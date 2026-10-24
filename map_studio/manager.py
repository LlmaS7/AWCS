"""Loopback-only standalone map library service, with bounded background jobs."""
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import subprocess
import sys
from threading import Lock, Thread
from urllib.parse import urlsplit, parse_qs, unquote
from uuid import uuid4

from .generator import generate, VERSION
from .storage import Library, MAX_BYTES, ROOT


class Service:
    def __init__(self, library=None):
        self.library = library or Library()
        self.jobs,self.children = {},set()
        self.lock = Lock()
        self.pool = ThreadPoolExecutor(max_workers=1,thread_name_prefix='map-studio')
        self.closed = False

    def bridge(self, definition, probe=False, robots=None, seed=0):
        payload = json.dumps(dict(definition=definition,probe=probe,robots=robots,seed=seed),ensure_ascii=False).encode('utf-8')
        if len(payload)>MAX_BYTES+8192: raise ValueError('地图超过2 MB')
        allowed = {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','PATHEXT'}
        env = {k:v for k,v in os.environ.items() if k.upper() in allowed}
        env['PYTHONIOENCODING'] = 'utf-8'
        with self.lock:
            if self.closed: raise ValueError('管理器已关闭')
            process = subprocess.Popen([sys.executable,'-I',str(ROOT/'bridge.py')],stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,
                                       creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.children.add(process)
        try:
            try: output,error = process.communicate(payload,timeout=90 if probe else 15)
            except subprocess.TimeoutExpired:
                process.kill();process.communicate()
                raise ValueError('试运行或校验超时；未修改当前仿真')
            if process.returncode: raise ValueError('校验子进程异常，请查看地图工具安装位置')
            result = json.loads(output.decode('utf-8'))
            if not result.get('ok'): raise ValueError(result.get('error','地图检查失败'))
            return result['analysis']
        finally:
            with self.lock: self.children.discard(process)

    def submit(self, operation, data):
        if operation not in ('generate','validate','probe'): raise ValueError('未知后台操作')
        with self.lock:
            if self.closed: raise ValueError('管理器已关闭')
            if any(job['status']=='running' for job in self.jobs.values()):
                raise ValueError('已有生成或试运行任务，请等待完成')
            while len(self.jobs)>=32: self.jobs.pop(next(iter(self.jobs)))
            key = uuid4().hex
            self.jobs[key] = dict(id=key,status='running',operation=operation)
        def work():
            try:
                definition = generate(**data.get('parameters',{})) if operation=='generate' else data['definition']
                analysis = self.bridge(definition,operation=='probe',data.get('robots'),data.get('seed',0))
                if operation=='probe':
                    folder = (self.library.root/'reports').resolve()
                    if not folder.is_relative_to(self.library.root): raise ValueError('试运行报告目录越界')
                    folder.mkdir(parents=True,exist_ok=True)
                    report = folder/(analysis['sha256']+'_'+key[:8]+'.json')
                    report.write_text(json.dumps(analysis,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                result = dict(status='done',definition=definition,analysis=analysis)
            except Exception as exc: result = dict(status='error',error=str(exc))
            with self.lock: self.jobs[key].update(result)
        self.pool.submit(work)
        return dict(id=key,status='running')

    def job(self, key):
        with self.lock:
            if key not in self.jobs: raise ValueError('后台任务不存在或已过期')
            return dict(self.jobs[key])

    def close(self):
        with self.lock:
            self.closed = True
            for child in self.children:
                if child.poll() is None: child.kill()
        self.pool.shutdown(wait=True,cancel_futures=True)


class Handler(BaseHTTPRequestHandler):
    def __init__(self,*args,service=None,**kwargs):
        self.service = service
        super().__init__(*args,**kwargs)

    def log_message(self,*_): pass

    def local(self):
        try:
            host = urlsplit('http://'+self.headers.get('Host',''))
            return host.hostname in ('127.0.0.1','localhost') and host.port==self.server.server_port
        except ValueError: return False

    def send(self,status,value,kind='application/json; charset=utf-8',download=None):
        body = json.dumps(value,ensure_ascii=False).encode('utf-8') if not isinstance(value,bytes) else value
        self.send_response(status)
        self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if download: self.send_header('Content-Disposition',f'attachment; filename="{download}.json"')
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError): pass

    def do_GET(self):
        if not self.local(): self.send(403,dict(error='仅接受本机服务地址'));return
        parsed = urlsplit(self.path);path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        try:
            if path=='/api/catalog': self.send(200,dict(maps=self.service.library.catalog(),generator=VERSION));return
            if path=='/api/job': self.send(200,self.service.job(query.get('id',[''])[0]));return
            if path in ('/api/map','/api/export'):
                key,scope = query.get('id',[''])[0],query.get('scope',['library'])[0]
                value = self.service.library.get(scope,key)
                self.send(200,value,download=key if path=='/api/export' else None);return
            static = ROOT/'frontend'
            target = (static/('index.html' if path=='/' else path.lstrip('/'))).resolve()
            if not target.is_relative_to(static.resolve()) or not target.is_file():
                self.send(404,dict(error='页面不存在'));return
            kind = 'text/javascript' if target.suffix=='.js' else mimetypes.guess_type(target)[0] or 'application/octet-stream'
            self.send(200,target.read_bytes(),kind+'; charset=utf-8')
        except (ValueError,KeyError,TypeError,OSError) as exc: self.send(400,dict(error=str(exc)))

    def do_POST(self):
        if not self.local(): self.send(403,dict(error='仅接受本机服务地址'));return
        origin = self.headers.get('Origin')
        if origin and origin != 'http://'+self.headers.get('Host',''):
            self.send(403,dict(error='拒绝跨站写入'));return
        if self.headers.get_content_type()!='application/json':
            self.send(415,dict(error='需要JSON请求'));return
        try:
            size = int(self.headers.get('Content-Length','0'))
            if not 0 < size <= MAX_BYTES+8192: raise ValueError('请求为空或超过2 MB')
            data = json.loads(self.rfile.read(size).decode('utf-8-sig'))
            if not isinstance(data,dict): raise ValueError('参数须为JSON对象')
            action = urlsplit(self.path).path.removeprefix('/api/')
            if action in ('generate','validate','probe'):
                self.send(202,self.service.submit(action,data));return
            library = self.service.library
            if action=='save':
                self.service.bridge(data['definition'])
                result = library.save(data['id'],data['definition'],data.get('name'))
            elif action=='rename': result = library.rename(data['id'],data['name'])
            elif action=='archive': result = library.archive(data['id'])
            elif action=='publish':
                definition = library.get('library',data['id'])
                self.service.bridge(definition)
                result = library.publish(data['id'],data['target_id'],definition)
            else: self.send(404,dict(error='操作不存在'));return
            self.send(200,result)
        except (ValueError,KeyError,TypeError,OSError) as exc: self.send(400,dict(error=str(exc)))


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True
    def server_close(self):
        super().server_close()
        self.service.close()


def start_server(port=0,library=None):
    service = Service(library)
    try: server = StudioServer(('127.0.0.1',port),partial(Handler,service=service))
    except Exception:
        service.close();raise
    server.service = service
    Thread(target=server.serve_forever,name='map-studio-http',daemon=True).start()
    return server,f'http://127.0.0.1:{server.server_port}/'

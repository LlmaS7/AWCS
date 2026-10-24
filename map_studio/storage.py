"""Bounded, local map library. New saves and publishes never overwrite a map."""
from copy import deepcopy
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from threading import RLock
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 2*1024*1024


def identity(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',value):
        raise ValueError('文件标识须为1～80位英文字母、数字、下划线或短横线')
    return value


def title(value):
    if not isinstance(value,str) or not value.strip() or len(value)>100 or any(ord(c)<32 for c in value):
        raise ValueError('名称须为1～100字符且不能含控制字符')
    return value.strip()


def read(path):
    if path.stat().st_size > MAX_BYTES: raise ValueError('地图超过2 MB')
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value,dict): raise ValueError('地图须为JSON对象')
    return value


def atomic_new(path, value):
    """Hard-link a complete sibling temporary file; existing destinations fail."""
    path.parent.mkdir(parents=True,exist_ok=True)
    with NamedTemporaryFile(dir=path.parent,prefix='.writing-',suffix='.tmp',delete=False) as stream:
        temporary = Path(stream.name)
        stream.write((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
        stream.flush(); os.fsync(stream.fileno())
    try:
        os.link(temporary,path)
    except FileExistsError as exc:
        raise ValueError('同名地图已存在，请换一个文件标识；原地图未覆盖') from exc
    finally: temporary.unlink(missing_ok=True)


class Library:
    def __init__(self, root=ROOT/'library', target=ROOT.parent/'maps'):
        self.root,self.target = Path(root).resolve(),Path(target).resolve()
        self.lock = RLock()

    def path(self, scope, key):
        folders = {'library':self.root,'archive':self.root/'archive','app':self.target}
        if scope not in folders: raise ValueError('未知地图分组')
        base = folders[scope].resolve()
        if scope=='archive' and not base.is_relative_to(self.root):
            raise ValueError('归档目录路径越界')
        candidate = base/(identity(key)+'.json')
        if candidate.is_symlink(): raise ValueError('地图库不接受符号链接')
        path = candidate.resolve()
        if not path.is_relative_to(base): raise ValueError('地图路径越界')
        return path

    def get(self, scope, key):
        with self.lock: return read(self.path(scope,key))

    def catalog(self):
        entries = []
        with self.lock:
            for scope,folder in [('library',self.root),('app',self.target),('archive',self.root/'archive')]:
                for path in sorted(folder.glob('*.json')):
                    try:
                        value = self.get(scope,path.stem)
                        grid = value['grid']
                        entries.append(dict(scope=scope,id=path.stem,name=value['name'],
                                            width=grid['width'],height=grid['height'],
                                            max_robots=value.get('robots',{}).get('max_count',len(value['points']['starts'])),
                                            available=True))
                    except (ValueError,OSError,KeyError,TypeError) as exc:
                        entries.append(dict(scope=scope,id=path.stem,name=path.stem,available=False,error=str(exc)))
        return entries

    def save(self, key, definition, name=None):
        value = deepcopy(definition)
        value['name'] = title(name if name is not None else value.get('name'))
        with self.lock: atomic_new(self.path('library',key),value)
        return dict(id=key,scope='library',definition=value)

    def rename(self, key, name):
        with self.lock:
            path = self.path('library',key)
            value = read(path);value['name'] = title(name)
            with NamedTemporaryFile(dir=path.parent,prefix='.rename-',suffix='.tmp',delete=False) as stream:
                temporary = Path(stream.name)
                stream.write((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
            try: os.replace(temporary,path)
            finally: temporary.unlink(missing_ok=True)
        return dict(id=key,scope='library',definition=value)

    def archive(self, key):
        with self.lock:
            source = self.path('library',key)
            dest_key = key[:60]+'_'+uuid4().hex[:8]
            destination = self.path('archive',dest_key)
            destination.parent.mkdir(parents=True,exist_ok=True)
            os.link(source,destination);source.unlink()
        return dict(id=dest_key,scope='archive')

    def publish(self, key, target_id, definition=None):
        with self.lock:
            value = deepcopy(definition) if definition is not None else self.get('library',key)
            if not self.target.is_dir(): raise ValueError('未找到 v0.4 maps 目录')
            atomic_new(self.path('app',target_id),value)
        return dict(id=target_id,scope='app',message='已导出到 v0.4；请在调试窗口刷新地图列表，再应用并重置。')

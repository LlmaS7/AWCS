"""Import orchestration. All store access shares the AI lifecycle lock."""
from concurrent.futures import TimeoutError
from copy import deepcopy
from threading import Thread
from time import monotonic
import json

from ai.provider import CancelToken, Stopped
from .documents import read_document
from .drafts import DraftStore
from .prompts import SYSTEM, OUTPUT_TOOL
from .schema import fields, text, boolean, validate_extraction


class ImportService:
    def __init__(self, ai):
        self.ai = ai
        self.store = DraftStore()

    def binding(self):
        c = self.ai.controller
        state = c.state()
        return {'run_id': c.run_id, 'generation': state['generation'], 'map_hash': state['map']['hash']}

    def check_scene(self, document):
        if any(document[k] != v for k, v in self.binding().items()):
            document['state'] = 'invalid'
            raise ValueError('工作场景已变化，旧草稿只能查看，请重新导入')

    def invalidate(self):
        if self.store.current:
            self.store.current['state'] = 'invalid'

    def clear(self):
        self.store.current = None

    def upload(self, name, data, generation):
        self.ai.sync_scene()
        with self.ai.lock:
            if self.ai.closed.is_set() or self.ai.active:
                raise ValueError('请等待当前请求完成，附件不会自动排队')
            binding = self.binding()
            if type(generation) is not int or generation != binding['generation']:
                raise ValueError('工作场景已变化，请重新选择文件')
            # Bounded local parse only; never wait for the actor/network under this lock.
            document = read_document(name, data)
            if binding != self.binding():
                raise ValueError('读取期间工作场景已变化，请重新导入')
            return self.store.install(document, binding)

    def begin_analysis(self, data):
        fields(data, ('document_id', 'instruction', 'generation', 'reimport_ack'), ('document_id', 'generation'))
        d = self.store.require(data['document_id'])
        self.check_scene(d)
        if type(data['generation']) is not int or data['generation'] != d['generation']:
            raise ValueError('工作场景已更新')
        if d['state'] not in ('uploaded', 'error'):
            raise ValueError('已有完整草稿或分析正在进行，不能重复分析')
        if d['duplicates'] and not boolean(data.get('reimport_ack', False)):
            raise ValueError('相同文件已导入，请先查看原结果并明确再次导入')
        d['instruction'] = text(data.get('instruction', ''), '附件说明', 6000).strip()
        d['state'], d['error'] = 'analyzing', ''

    def extract(self, request, data):
        ai = self.ai
        with ai.lock:
            d = deepcopy(self.store.require(data['document_id']))
        locations = ai.tool(request, 'get_locations', {}, request['id'] + '/locations')
        compact = {kind: [{k: v for k, v in p.items() if k in ('id', 'name', 'aliases', 'pickup_id')}
                          for p in locations[kind]] for kind in ('pickup', 'delivery', 'shelf')}
        content = json.dumps({'instruction': d['instruction'], 'locations': compact,
                              'blocks': [{'id': b['id'], 'text': b['text'], 'locator': b['locator']}
                                         for b in d['blocks']]}, ensure_ascii=False)
        capacity = request['cfg'].get('context_window') or 64000
        reserve = min(8192, request['cfg'].get('max_output_tokens') or 8192)
        # This is a local estimate, not a tokenizer or a capacity guarantee.
        if len((SYSTEM + content).encode('utf-8')) > min(256000, max(0, capacity - reserve) * 2):
            raise ValueError('文件、说明和地点表超过当前模型的本地预算，请拆分文件或换更大上下文模型；没有截断')
        ai.emit('import_progress', request_id=request['id'], stage='正在分析文件；确认前不会创建任务')
        reply, _ = ai.provider.chat(request['cfg'], [{'role': 'system', 'content': SYSTEM},
                                                     {'role': 'user', 'content': content}],
                                    [OUTPUT_TOOL], request['token'])
        ai.fresh(request)
        calls = reply.get('tool_calls', [])
        if len(calls) != 1 or calls[0].get('function', {}).get('name') != 'propose_import_draft':
            raise ValueError('模型未完整返回预期草稿，未执行任何业务；请重试或调整模型')
        raw = json.loads(calls[0]['function']['arguments'])
        candidates, excluded = validate_extraction(raw, d, locations, d['instruction'])
        with ai.lock:
            ai.fresh(request)
            current = self.store.require(d['document_id'])
            self.check_scene(current)
            current.update(candidates=candidates, excluded=excluded, locations=compact,
                           model=request['cfg']['model'], state='ready', revision=current['revision'] + 1)
            ai.emit('import_ready', request_id=request['id'], draft_id=current['draft_id'],
                    generation=current['generation'], count=len(candidates))

    def analysis_failed(self, request, message):
        d = self.store.current
        if d and d['state'] == 'analyzing':
            d.update(state='error', error=message)

    def draft(self, identity=None):
        self.ai.sync_scene()
        with self.ai.lock:
            if identity:
                self.store.require(identity)
            return self.store.public()

    def source(self, document_id, block_id):
        with self.ai.lock:
            d = self.store.require(document_id)
            if block_id == 'instruction' and d['instruction']:
                return {'text': d['instruction'], 'locator': {'type': 'instruction'}}
            block = next((b for b in d['blocks'] if b['id'] == block_id), None)
            if block is None:
                raise ValueError('来源已清除或不存在')
            return deepcopy(block)

    def edit(self, data):
        self.ai.sync_scene()
        with self.ai.lock:
            d = self.store.require(data.get('draft_id'))
            self.check_scene(d)
            if self.ai.active:
                raise ValueError('请等待当前请求完成后再修改草稿')
            return self.store.edit(data)

    def discard(self, data):
        fields(data, ('draft_id',), ('draft_id',))
        with self.ai.lock:
            self.store.require(data['draft_id'])
            if self.ai.active:
                raise ValueError('请先停止并等待当前结果核实，再放弃草稿')
            self.clear()
            return {'draft': None}

    def commit(self, data):
        ai = self.ai
        ai.sync_scene()
        with ai.lock:
            fields(data, ('draft_id', 'expected_revision', 'confirmation_id', 'selections'),
                   ('draft_id', 'expected_revision', 'confirmation_id', 'selections'))
            text(data['confirmation_id'], '确认标识', 80)
            if type(data['expected_revision']) is not int:
                raise ValueError('草稿版本必须为整数')
            # Historical retries remain queryable after clear/reset/other active work.
            known = data.get('confirmation_id') in self.store.operations
            d = self.store.current
            known_version = (d is not None and data.get('draft_id') == d['draft_id']
                             and data.get('expected_revision') in d['submitted_versions'])
            if not known and not known_version:
                if ai.closed.is_set() or ai.active:
                    raise ValueError('请等待当前请求完成，创建请求不会自动排队')
                self.check_scene(self.store.require(data.get('draft_id')))
            record, created = self.store.prepare_commit(data)
            if not created:
                return self.store.public_operation(record)
            cfg = ai.configuration.snapshot()
            request = {'id': record['request_id'], 'kind': 'import_commit', 'session': ai.session,
                       'generation': record['generation'], 'token': CancelToken(cfg['timeout']),
                       'cfg': cfg, 'conversation': None}
            ai.active = request
            ai.emit('start', request_id=request['id'], job='import_commit', generation=record['generation'],
                    filename=self.store.current['filename'])
            Thread(target=ai._work, args=(request, {'submission_id': record['submission_id']}),
                   name='import-commit', daemon=True).start()
            return self.store.public_operation(record)

    def execute(self, request, data):
        ai = self.ai
        with ai.lock:
            record = self.store.operations[data['submission_id']]
            items = deepcopy(record['items'])
        args = {'tasks': [{k: item[k] for k in ('pickup_id', 'delivery_id', 'priority')} for item in items]}
        def valid():
            # Called by actor: no locks, network, or Future waiting here.
            return (not request['token'].event.is_set() and not ai.closed.is_set()
                    and monotonic() < request['token'].deadline and ai.active is request
                    and ai.controller.generation == request['generation'])
        def progress(result):
            with ai.lock:
                record['result'] = deepcopy(result)
            ai.emit('import_progress', request_id=request['id'], stage='正在逐项创建并规划路线',
                    completed=sum(a.get('outcome') == 'applied' for a in result['actions']), total=len(items))
        try:
            try:
                future = ai.controller.submit('_ai_business', {
                    'name': 'create_tasks', 'arguments': args, 'generation': request['generation'],
                    'operation_id': request['id'], 'sources': [item['source'] for item in items],
                    'valid': valid, 'on_progress': progress})
            except Exception:
                # submit() raises before queue acceptance. This batch has no domain effects.
                result = {'status': 'finished', 'error': '创建请求未受理，请稍后重新确认', 'actions': [
                    {'operation': 'add', 'outcome': 'not_executed', 'reason': '未受理，未创建任务'} for _ in items]}
                with ai.lock:
                    self.store.finish(record, result)
                ai.emit('result', request_id=request['id'], generation=request['generation'],
                        tool='create_tasks', result=result, submission_id=record['submission_id'])
                return
            # Cancellation stops future items, but we still collect the actor's receipt.
            while True:
                try:
                    result = future.result(timeout=.1)
                    break
                except TimeoutError:
                    if monotonic() >= request['token'].deadline:
                        request['token'].event.set()
            with ai.lock:
                self.store.finish(record, result)
            ai.emit('result', request_id=request['id'], generation=request['generation'],
                    tool='create_tasks', result=result, submission_id=record['submission_id'])
        except Exception:
            with ai.lock:
                record['status'] = 'unknown'
            raise

    def operation(self, identity):
        with self.ai.lock:
            record = self.store.operations.get(identity)
            if record is None:
                return {'status': 'unknown', 'error': '未找到本次提交记录，请核实任务，不要自动重复创建'}
            uncertain = record['status'] == 'unknown'
            query = {'operation_id': record['submission_id'], 'generation': record['generation'],
                     'items': deepcopy(record['items'])} if uncertain else None
        if uncertain:
            try:
                result = self.ai.controller.submit('_import_reconcile', query).result(timeout=2)
                if result.get('status') == 'finished':
                    with self.ai.lock:
                        self.store.finish(record, result)
            except Exception:
                pass  # Still unknown: never unlock occurrences or automatically resubmit.
        with self.ai.lock:
            return self.store.public_operation(record)

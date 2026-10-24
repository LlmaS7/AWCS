"""Runtime-only identity and receipts. Caller holds AIService.lock."""
from copy import deepcopy
from uuid import uuid4
import json
import re

from .limits import MAX_BATCHES, MAX_OCCURRENCES, MAX_SUBMISSIONS
from .schema import fields, text, integer, boolean, candidate_state, validate_source


class DraftStore:
    def __init__(self):
        self.current = None
        self.history = []
        self.operations = {}

    def install(self, document, binding):
        if self.current is not None:
            raise ValueError('已有附件或草稿，请先明确放弃后再导入新文件')
        if len(self.history) >= MAX_BATCHES:
            raise ValueError('本次运行导入批次已达256上限，已有防重复记录仍保留')
        identity = uuid4().hex
        duplicates = [deepcopy(v) for v in self.history if v['sha256'] == document['sha256']]
        self.current = {**document, **binding, 'document_id': identity, 'draft_id': identity,
                        'revision': 0, 'state': 'uploaded', 'instruction': '', 'model': '',
                        'candidates': [], 'excluded': [], 'locations': {}, 'error': '',
                        'duplicates': duplicates, 'submitted_versions': {}, 'accepted': 0}
        self.history.append({'document_id': identity, 'filename': document['filename'],
                             'sha256': document['sha256'], 'generation': binding['generation'],
                             'submissions': []})
        return self.public()

    def require(self, identity=None):
        d = self.current
        if d is None or (identity is not None and d['draft_id'] != identity):
            raise ValueError('附件或草稿已清除，请重新导入')
        return d

    def public(self):
        if self.current is None:
            return {'draft': None}
        d = self.current
        result = {k: deepcopy(v) for k, v in d.items()
                  if k not in ('blocks', 'submitted_versions', 'accepted', 'run_id')}
        # Private reservations/applied identities are never accepted back from a client.
        for row in result['candidates']:
            row['problems'] = candidate_state(row)
            row['ready'] = not row['problems'] and not row['deleted'] and d['state'] == 'ready'
            row['created_count'] = len(row.pop('applied'))
            row['reserved_count'] = len(row.pop('reserved'))
            row['remaining'] = max(0, (row['count'] or 0) - row['created_count'] - row['reserved_count'])
            row['ready'] = row['ready'] and row['remaining'] > 0
            row.pop('next_index')
        signatures = {}
        for row in result['candidates']:
            signature = (row['pickup_id'], row['delivery_id'], row['priority'])
            if None not in signature and not row['deleted']:
                signatures.setdefault(signature, []).append(row['candidate_id'])
        for row in result['candidates']:
            row['similar'] = [x for x in signatures.get((row['pickup_id'], row['delivery_id'], row['priority']), [])
                              if x != row['candidate_id']]
        result['operations'] = [self.public_operation(v) for v in self.operations.values()
                                if v['draft_id'] == d['draft_id']]
        return {'draft': result}

    @staticmethod
    def public_operation(record):
        return deepcopy({k: record[k] for k in ('submission_id', 'draft_id', 'generation', 'status',
                                                'request_id', 'items', 'result')})

    def edit(self, data):
        fields(data, ('draft_id', 'expected_revision', 'candidate_id', 'changes'),
               ('draft_id', 'expected_revision', 'candidate_id', 'changes'))
        d = self.require(data['draft_id'])
        if d['state'] != 'ready' or type(data['expected_revision']) is not int or data['expected_revision'] != d['revision']:
            raise ValueError('草稿状态或版本已变化，请刷新后修改')
        row = next((r for r in d['candidates'] if r['candidate_id'] == data['candidate_id']), None)
        if row is None or row['deleted']:
            raise ValueError('不存在此候选，不能新增无来源任务')
        changes = data['changes']
        fields(changes, ('pickup_id', 'delivery_id', 'priority', 'count', 'reviewed', 'ignore_constraints', 'deleted'))
        updated = deepcopy(row)
        for key, value in changes.items():
            if key in ('pickup_id', 'delivery_id'):
                group = 'pickup' if key == 'pickup_id' else 'delivery'
                if value is not None and (not isinstance(value, str) or value not in {p['id'] for p in d['locations'][group]}):
                    raise ValueError('请选择当前地图正式作业点')
            elif key == 'priority':
                integer(value, '等级', 1, 5)
            elif key == 'count':
                if value is not None:
                    integer(value, '搬运次数')
                if row['applied'] and (value is None or value < len(row['applied'])):
                    raise ValueError('目标次数不能少于已创建次数')
            else:
                boolean(value)
            updated[key] = value
        updated['human_edited'] = updated['human_edited'] or any(row[k] != updated[k] for k in changes)
        row.update(updated)
        d['revision'] += 1
        return self.public()

    def prepare_commit(self, data):
        fields(data, ('draft_id', 'expected_revision', 'confirmation_id', 'selections'),
               ('draft_id', 'expected_revision', 'confirmation_id', 'selections'))
        identity = text(data['confirmation_id'], '确认标识', 80)
        if not re.fullmatch('[A-Za-z0-9_-]{16,80}', identity):
            raise ValueError('确认标识无效')
        revision = integer(data['expected_revision'], '草稿版本', 0, 10**9)
        selections = data['selections']
        if not isinstance(selections, list) or not 1 <= len(selections) <= 20:
            raise ValueError('请选择1至20项搬运')
        normalized, seen, total = [], set(), 0
        for selection in selections:
            fields(selection, ('candidate_id', 'count'), ('candidate_id', 'count'))
            candidate_id = text(selection['candidate_id'], '候选标识', 80)
            if candidate_id in seen:
                raise ValueError('同一候选不能重复选择')
            count = integer(selection['count'], '本次搬运次数', 1, 20)
            seen.add(candidate_id)
            total += count
            normalized.append({'candidate_id': candidate_id, 'count': count})
        if total > 20:
            raise ValueError('本次展开后超过20项，请减少选择或次数')
        fingerprint = json.dumps([data['draft_id'], revision, normalized], sort_keys=True)
        old = self.operations.get(identity)
        if old is not None:
            if old['fingerprint'] != fingerprint:
                raise ValueError('同一确认标识不能使用不同参数')
            return old, False
        d = self.require(data['draft_id'])
        old_id = d['submitted_versions'].get(revision)
        if old_id:
            old = self.operations[old_id]
            if old['fingerprint'] != fingerprint:
                raise ValueError('此版本已确认，请查询结果并刷新草稿后再选择')
            return old, False
        if d['state'] != 'ready' or revision != d['revision']:
            raise ValueError('草稿已变化或不能提交，请刷新后确认')
        if len([v for v in self.operations.values() if v['draft_id'] == d['draft_id']]) >= MAX_SUBMISSIONS or d['accepted'] + total > MAX_OCCURRENCES:
            raise ValueError('本批次提交记录或累计搬运达到资源上限，已有回执保留')
        rows = {r['candidate_id']: r for r in d['candidates']}
        items = []
        for selection in normalized:
            row = rows.get(selection['candidate_id'])
            if row is None or row['deleted'] or candidate_state(row):
                raise ValueError('所选候选未就绪，请补齐地点、次数并处理执行约束')
            if selection['count'] > row['count'] - len(row['applied']) - len(row['reserved']):
                raise ValueError('本次次数超过确定未创建的剩余次数')
            for index in range(row['next_index'], row['next_index'] + selection['count']):
                refs = {b['id']: b['locator'] for b in d['blocks']}
                refs['instruction'] = {'type': 'instruction'}
                source = validate_source({'kind': 'file_import', 'filename': d['filename'], 'sha256': d['sha256'],
                                          'import_batch_id': d['document_id'], 'candidate_id': row['candidate_id'],
                                          'occurrence_index': index, 'locators': [refs[k] for k in row['source_ids']],
                                          'human_edited': row['human_edited']})
                items.append({'candidate_id': row['candidate_id'], 'occurrence_index': index,
                              'pickup_id': row['pickup_id'], 'delivery_id': row['delivery_id'],
                              'priority': row['priority'], 'source': source})
        record = {'submission_id': identity, 'draft_id': d['draft_id'], 'generation': d['generation'],
                  'request_id': identity, 'fingerprint': fingerprint, 'status': 'running',
                  'items': items, 'result': None}
        self.operations[identity] = record
        d['submitted_versions'][revision] = identity
        d['accepted'] += total
        d['state'] = 'submitting'
        for item in items:
            row = rows[item['candidate_id']]
            row['reserved'].append(item['occurrence_index'])
            row['next_index'] = max(row['next_index'], item['occurrence_index'] + 1)
        self.history[-1]['submissions'].append(identity)
        return record, True

    def finish(self, record, result):
        if record['status'] == 'finished':
            return
        record['result'] = deepcopy(result)
        actions = result.get('actions', [])
        if result.get('status') != 'finished' or len(actions) != len(record['items']):
            record['status'] = 'unknown'
            return
        record['status'] = 'finished'
        d = self.current
        if d is None or d['draft_id'] != record['draft_id']:
            return
        rows = {r['candidate_id']: r for r in d['candidates']}
        for item, action in zip(record['items'], actions):
            row = rows[item['candidate_id']]
            if item['occurrence_index'] in row['reserved']:
                row['reserved'].remove(item['occurrence_index'])
            if action.get('outcome') == 'applied':
                row['applied'].append(item['occurrence_index'])
        if d['state'] != 'invalid':
            d['state'] = 'ready'
        d['revision'] += 1

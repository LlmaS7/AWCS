"""Strict transport contracts. Model statements never grant submission rights."""
from copy import deepcopy
import re
from .limits import MAX_CANDIDATES, MAX_NOTES, MAX_OCCURRENCES


def fields(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise ValueError('导入数据字段缺失或包含不支持的字段')


def text(value, label, maximum=500):
    if not isinstance(value, str) or len(value) > maximum:
        raise ValueError(f'{label}格式或长度无效')
    return value


def integer(value, label, low=1, high=MAX_OCCURRENCES):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label}须为{low}至{high}的整数')
    return value


def boolean(value):
    if type(value) is not bool:
        raise ValueError('确认标记必须为布尔值')
    return value


def notes(value):
    if not isinstance(value, list) or len(value) > MAX_NOTES:
        raise ValueError('说明条数超限')
    return [text(v, '说明', 300) for v in value]


def validate_source(value):
    if value is None:
        return None
    fields(value, ('kind', 'filename', 'sha256', 'import_batch_id', 'candidate_id',
                   'occurrence_index', 'locators', 'human_edited'),
           ('kind', 'filename', 'sha256', 'import_batch_id', 'candidate_id',
            'occurrence_index', 'locators', 'human_edited'))
    if value['kind'] != 'file_import' or not re.fullmatch(r'[0-9a-f]{64}', text(value['sha256'], '摘要', 64)):
        raise ValueError('文件来源标识无效')
    filename = text(value['filename'], '来源文件名', 240)
    if not filename or any(c in filename for c in '\\/') or any(ord(c) < 32 for c in filename):
        raise ValueError('来源文件名无效')
    for key in ('import_batch_id', 'candidate_id'):
        if not re.fullmatch('[A-Za-z0-9_-]{1,80}', text(value[key], '来源ID', 80)):
            raise ValueError('来源ID无效')
    integer(value['occurrence_index'], '搬运序号')
    boolean(value['human_edited'])
    locators = value['locators']
    if not isinstance(locators, list) or not 1 <= len(locators) <= 12:
        raise ValueError('来源位置无效')
    for locator in locators:
        fields(locator, ('type', 'line', 'paragraph', 'table', 'row', 'column', 'parent'), ('type',))
        kind = locator['type']
        required = {'text_line': ('line',), 'docx_paragraph': ('paragraph',),
                    'docx_table': ('table', 'row', 'column'), 'instruction': ()}
        if not isinstance(kind, str) or kind not in required or any(k not in locator for k in required[kind]):
            raise ValueError('来源位置类型无效')
        if set(locator) - {'type', *required[kind], *(['parent'] if kind == 'docx_table' else [])}:
            raise ValueError('来源位置包含无关字段')
        for key in required[kind]:
            integer(locator[key], '来源位置', high=20000)
        if 'parent' in locator and not re.fullmatch(r'[0-9/]{1,80}', text(locator['parent'], '父表格位置', 80)):
            raise ValueError('父表格位置无效')
    return deepcopy(value)


def candidate_state(row):
    problems = []
    if row['pickup_id'] is None:
        problems.append('请选择取货点')
    if row['delivery_id'] is None:
        problems.append('请选择配送点')
    if row['count'] is None:
        problems.append('请补充搬运次数；货物数量不等于搬运次数')
    if row['issues'] and not row['reviewed']:
        problems.append('请核对并确认识别疑点')
    if row['constraints'] and not row['ignore_constraints']:
        problems.append('请明确接受本次忽略未支持的执行约束')
    return problems


def validate_extraction(value, document, locations, instruction):
    fields(value, ('candidates', 'excluded'), ('candidates', 'excluded'))
    candidates = value['candidates']
    if not isinstance(candidates, list) or len(candidates) > MAX_CANDIDATES:
        raise ValueError('需求候选超过100条，请拆分文件；没有截断处理')
    blocks = {b['id']: b for b in document['blocks']}
    allowed_sources = set(blocks) | ({'instruction'} if instruction else set())
    pickups = {p['id'] for p in locations['pickup']}
    deliveries = {p['id'] for p in locations['delivery']}
    result = []
    for index, raw in enumerate(candidates, 1):
        fields(raw, ('source_ids', 'pickup_id', 'delivery_id', 'priority', 'count', 'quantity_kind',
                     'quantity_text', 'issues', 'constraints', 'notes', 'overrides'),
               ('source_ids', 'pickup_id', 'delivery_id', 'quantity_kind', 'count'))
        refs = raw['source_ids']
        if (not isinstance(refs, list) or not 1 <= len(refs) <= 12
                or any(not isinstance(x, str) or x not in allowed_sources for x in refs)
                or not any(x in blocks for x in refs)):
            raise ValueError('模型返回了不存在或无文件依据的来源，未生成草稿')
        if raw['pickup_id'] is not None and (not isinstance(raw['pickup_id'], str) or raw['pickup_id'] not in pickups):
            raise ValueError('模型返回了不存在的取货点，未生成草稿')
        if raw['delivery_id'] is not None and (not isinstance(raw['delivery_id'], str) or raw['delivery_id'] not in deliveries):
            raise ValueError('模型返回了不存在的配送点，未生成草稿')
        kind = raw['quantity_kind']
        if kind not in ('trips', 'goods', 'unspecified', 'unknown'):
            raise ValueError('数量含义无效')
        count = raw['count']
        if count is not None:
            integer(count, '搬运次数')
        if kind == 'unspecified':
            count = 1
        elif kind in ('goods', 'unknown'):
            count = None
        result.append({'candidate_id': f'c{index}', 'source_ids': list(dict.fromkeys(refs)),
                       'pickup_id': raw['pickup_id'], 'delivery_id': raw['delivery_id'],
                       'priority': integer(raw.get('priority', 2), '等级', 1, 5), 'count': count,
                       'quantity_kind': kind, 'quantity_text': text(raw.get('quantity_text', ''), '原数量描述', 300),
                       'issues': notes(raw.get('issues', [])), 'constraints': notes(raw.get('constraints', [])),
                       'notes': notes(raw.get('notes', [])), 'overrides': notes(raw.get('overrides', [])),
                       'reviewed': False, 'ignore_constraints': False, 'human_edited': False,
                       'deleted': False, 'applied': [], 'next_index': 1, 'reserved': []})
    excluded = value['excluded']
    if not isinstance(excluded, list) or len(excluded) > MAX_CANDIDATES:
        raise ValueError('排除说明超限，请拆分文件')
    checked = []
    for item in excluded:
        fields(item, ('source_ids', 'reason'), ('source_ids', 'reason'))
        refs = item['source_ids']
        if not isinstance(refs, list) or not 1 <= len(refs) <= 12 or any(not isinstance(x, str) or x not in allowed_sources for x in refs):
            raise ValueError('排除说明引用了不存在的来源')
        checked.append({'source_ids': refs, 'reason': text(item['reason'], '排除原因', 300)})
    return result, checked

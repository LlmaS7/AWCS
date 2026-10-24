"""No disk extraction, external relationships, OCR, or executable Markdown."""
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile

from .limits import file_limit, TEXT_CHARS, ZIP_ENTRIES, ZIP_BYTES, XML_BYTES, XML_DEPTH

WORD_NS = {'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
           'http://purl.oclc.org/ooxml/wordprocessingml/main'}
REVISION_NAMES = {'ins', 'del', 'delText', 'delInstrText', 'conflictIns', 'conflictDel', 'moveFrom', 'moveTo', 'cellIns', 'cellDel', 'cellMerge',
                  'numberingChange', 'customXmlInsRangeStart', 'customXmlDelRangeStart',
                  'customXmlMoveFromRangeStart', 'customXmlMoveToRangeStart'}


def basename(name):
    if not isinstance(name, str):
        raise ValueError('文件名无效')
    name = name.replace('\\', '/').rsplit('/', 1)[-1]
    if not name or len(name) > 240 or any(ord(c) < 32 for c in name):
        raise ValueError('文件名须为1至240字符，不能包含控制字符')
    file_limit(name)
    return name


def local(tag):
    return tag.rsplit('}', 1)[-1]


def word(node):
    return node.tag.startswith('{') and node.tag[1:].split('}', 1)[0] in WORD_NS


def xml(data):
    # Decode before checking: UTF-16 XML must not bypass the declaration check.
    probe = data.replace(b'\x00', b'').upper()
    if b'<!DOCTYPE' in probe or b'<!ENTITY' in probe:
        raise ValueError('DOCX 包含不支持的 XML 声明')
    depth = 0
    for event, node in ET.iterparse(BytesIO(data), events=('start', 'end')):
        depth += 1 if event == 'start' else -1
        if depth > XML_DEPTH:
            raise ValueError('DOCX XML 层级过深，请简化文档')
        if event == 'start' and (word(node) or node.tag.startswith('{http://schemas.microsoft.com/office/word/')):
            tag = local(node.tag)
            if tag in REVISION_NAMES or tag.endswith('PrChange') or tag.startswith(('moveFromRange', 'moveToRange')):
                raise ValueError('DOCX 含未处理修订，请接受或拒绝修订后另存并导入')
    return ET.fromstring(data)


def decode(data):
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        encodings = ('utf-16',)
    else:
        encodings = ('utf-8-sig', 'gb18030')
    for encoding in encodings:
        try:
            value = data.decode(encoding)
            if '\x00' in value or any(ord(c) < 32 and c not in '\n\r\t' for c in value):
                continue
            return value, encoding
        except UnicodeError:
            pass
    raise ValueError('无法读取文本编码，请另存为 UTF-8 后重试')


def read_docx(data):
    warnings, blocks = [], []
    try:
        with ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > ZIP_ENTRIES or sum(i.file_size for i in infos) > ZIP_BYTES:
                raise ValueError('DOCX 结构或解压后体积超限，请简化文档')
            names = [i.filename for i in infos]
            if len(names) != len(set(names)) or 'word/document.xml' not in names or '[Content_Types].xml' not in names:
                raise ValueError('不是受支持的 DOCX 文件或包内路径重复')
            roots, consumed = {}, 0
            for info in infos:
                if info.flag_bits & 1 or '..' in PurePosixPath(info.filename).parts:
                    raise ValueError('不支持加密或路径异常的 DOCX')
                if 'vbaProject' in info.filename:
                    raise ValueError('不支持包含宏的文档，请另存普通 DOCX')
                if not info.filename.endswith(('.xml', '.rels')):
                    continue
                if info.file_size > XML_BYTES:
                    raise ValueError('DOCX 单个 XML 超过8 MiB，请简化文档')
                with archive.open(info) as stream:
                    raw = stream.read(XML_BYTES + 1)
                consumed += len(raw)
                if len(raw) > XML_BYTES or consumed > ZIP_BYTES:
                    raise ValueError('DOCX 实际解压体积超限')
                root = xml(raw)
                if info.filename in ('word/document.xml', '[Content_Types].xml'):
                    roots[info.filename] = root
                if info.filename.startswith(('word/header', 'word/footer', 'word/comments')):
                    warnings.append('页眉、页脚或批注未读取')
                if info.filename.endswith('.rels') and any(n.get('TargetMode') == 'External' for n in root):
                    warnings.append('外部链接内容未读取，不会访问链接')
            types = ET.tostring(roots['[Content_Types].xml'], encoding='unicode')
            if 'macroEnabled' in types or 'wordprocessingml.document.main+xml' not in types:
                raise ValueError('请使用普通 DOCX 文档，不支持此文档类型')
            root = roots['word/document.xml']
            for n in root.iter():
                tag = local(n.tag)
                if tag in ('drawing', 'pict', 'txbxContent', 'object', 'oMath', 'fldChar', 'fldSimple', 'altChunk'):
                    warnings.append('图片、文本框、公式、嵌入对象或动态域内容未读取，任务可能不完整')

            chars = 0
            def append(text, locator):
                nonlocal chars
                if text.strip():
                    chars += len(text)
                    if chars > TEXT_CHARS:
                        raise ValueError('提取正文超过20,000字符，请拆分文件')
                    blocks.append({'id': f'b{len(blocks)+1}', 'text': text, 'locator': locator})

            # Only direct document paragraphs/cells; do not collect textbox descendants.
            def paragraph(p):
                values = []
                field_depth = 0
                def walk(n):
                    nonlocal field_depth
                    tag = local(n.tag)
                    if tag in ('drawing', 'pict', 'txbxContent', 'object', 'oMath', 'fldSimple', 'instrText'):
                        return
                    if word(n) and tag == 'fldChar':
                        kind = next((v for k, v in n.attrib.items() if local(k) == 'fldCharType'), '')
                        if kind == 'begin':
                            field_depth += 1
                        elif kind == 'end':
                            field_depth = max(0, field_depth - 1)
                        return
                    if word(n) and tag == 't' and not field_depth:
                        values.append(n.text or '')
                    elif word(n) and tag in ('br', 'cr', 'tab'):
                        values.append('\t' if tag == 'tab' else '\n')
                    else:
                        for child in n:
                            walk(child)
                walk(p)
                return ''.join(values)

            table_no, paragraph_no = 0, 0
            def table(tbl, path=''):
                nonlocal table_no
                table_no += 1
                current = table_no
                for ri, tr in enumerate((n for n in tbl if word(n) and local(n.tag) == 'tr'), 1):
                    for ci, tc in enumerate((n for n in tr if word(n) and local(n.tag) == 'tc'), 1):
                        locator = {'type': 'docx_table', 'table': current, 'row': ri, 'column': ci}
                        if path:
                            locator['parent'] = path
                        for child in tc:
                            if word(child) and local(child.tag) == 'p':
                                append(paragraph(child), locator)
                            elif word(child) and local(child.tag) == 'tbl':
                                table(child, f'{current}/{ri}/{ci}')
            body = next((n for n in root if word(n) and local(n.tag) == 'body'), None)
            if body is None:
                raise ValueError('DOCX 缺少主文档正文')
            for n in body:
                if word(n) and local(n.tag) == 'p':
                    paragraph_no += 1
                    append(paragraph(n), {'type': 'docx_paragraph', 'paragraph': paragraph_no})
                elif word(n) and local(n.tag) == 'tbl':
                    table(n)
                elif local(n.tag) != 'sectPr':
                    warnings.append('未读取部分非标准正文结构，请核对原文或另存简化文档')
    except (BadZipFile, ET.ParseError, OSError, RuntimeError, NotImplementedError, EOFError) as exc:
        raise ValueError('DOCX 损坏或格式不支持，请另存普通 DOCX 后重试') from exc
    return blocks, sorted(set(warnings))


def read_document(name, data):
    name = basename(name)
    if not isinstance(data, bytes) or not 0 < len(data) <= file_limit(name):
        raise ValueError('文件为空或超过限制：MD/TXT 1 MiB，DOCX 10 MiB')
    extension = name.rsplit('.', 1)[-1].lower()
    warnings, encoding = [], None
    if extension == 'docx':
        blocks, warnings = read_docx(data)
    else:
        text, encoding = decode(data)
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        if len(text) > TEXT_CHARS:
            raise ValueError('提取正文超过20,000字符，请拆分文件')
        blocks = [{'id': f'b{i}', 'text': line, 'locator': {'type': 'text_line', 'line': i}}
                  for i, line in enumerate(text.split('\n'), 1) if line.strip()]
    if not blocks:
        raise ValueError('没有可读取正文；首版不识别图片，请提供正文或表格文字')
    return {'filename': name, 'size': len(data), 'sha256': sha256(data).hexdigest(),
            'format': extension, 'encoding': encoding, 'blocks': blocks, 'warnings': warnings}

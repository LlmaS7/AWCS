"""Bounded, runtime-local imports; ordinary chat limits remain unchanged."""
TEXT_BYTES = 1024 * 1024
DOCX_BYTES = 10 * 1024 * 1024
TEXT_CHARS = 20_000
MAX_CANDIDATES = 100
MAX_BATCHES = 256
MAX_OCCURRENCES = 2_000
MAX_SUBMISSIONS = 512
ZIP_ENTRIES = 2_048
ZIP_BYTES = 64 * 1024 * 1024
XML_BYTES = 8 * 1024 * 1024
XML_DEPTH = 64
MAX_NOTES = 20


def file_limit(filename):
    extension = filename.rsplit('.', 1)[-1].lower()
    if extension not in ('md', 'txt', 'docx'):
        raise ValueError('仅支持 MD、TXT 和 DOCX 文件')
    return DOCX_BYTES if extension == 'docx' else TEXT_BYTES

"""Build candidate JSONL manifests without writing knowledge-base records."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path


BODY_SUFFIXES = {'.pdf', '.caj', '.zip'}


def _stable_item_key(relative_path: str) -> str:
    return hashlib.sha256(relative_path.encode('utf-8')).hexdigest()[:24]


def _normalized_filename(value: str) -> str:
    value = str(value or '').replace('\\', '/')
    return Path(value).name.lower()


def parse_ris_metadata(root: Path):
    by_filename = {}
    for path in root.rglob('*.ris'):
        record = {}
        authors = []
        try:
            lines = path.read_text(encoding='utf-8-sig', errors='replace').splitlines()
        except OSError:
            continue
        for line in lines:
            match = re.match(r'^([A-Z0-9]{2})\s{0,2}-\s?(.*)$', line)
            if not match:
                continue
            tag, value = match.groups()
            value = value.strip()
            if tag == 'ER':
                filenames = record.pop('_filenames', [])
                if filenames:
                    record['authors'] = list(authors)
                    for filename in filenames:
                        by_filename[_normalized_filename(filename)] = dict(record)
                record, authors = {}, []
            elif tag in {'AU', 'A1'}:
                authors.append(value)
            elif tag in {'TI', 'T1'}:
                record['title'] = value
            elif tag in {'DO', 'M3'} and value.lower().startswith('10.'):
                record['doi'] = value
            elif tag in {'JO', 'JF', 'T2'}:
                record.setdefault('journal', value)
            elif tag in {'PY', 'Y1', 'DA'}:
                record.setdefault('publication_date', value[:10])
            elif tag in {'L1', 'L2', 'UR'}:
                if value.lower().endswith(('.pdf', '.caj')):
                    record.setdefault('_filenames', []).append(value)
    return by_filename


def parse_tabular_txt_metadata(root: Path):
    by_filename = {}
    filename_headers = {'filename', 'file', 'pdf', '文件名', '本地文件'}
    for path in root.rglob('*.txt'):
        try:
            sample = path.read_text(encoding='utf-8-sig', errors='replace')
        except OSError:
            continue
        first_line = sample.splitlines()[0] if sample.splitlines() else ''
        delimiter = '\t' if '\t' in first_line else ',' if ',' in first_line else None
        if not delimiter:
            continue
        try:
            rows = csv.DictReader(sample.splitlines(), delimiter=delimiter)
            fieldnames = [str(name or '').strip().lower() for name in (rows.fieldnames or [])]
            filename_field = next(
                (name for name in rows.fieldnames or [] if name.strip().lower() in filename_headers),
                None,
            )
            if not filename_field or not fieldnames:
                continue
            for row in rows:
                filename = _normalized_filename(row.get(filename_field))
                if not filename:
                    continue
                authors = row.get('authors') or row.get('作者') or ''
                by_filename[filename] = {
                    'title': row.get('title') or row.get('标题') or None,
                    'doi': row.get('doi') or row.get('DOI') or None,
                    'journal': row.get('journal') or row.get('期刊') or None,
                    'publication_date': row.get('publication_date') or row.get('年份') or None,
                    'authors': [item.strip() for item in re.split(r'[;,；]', authors) if item.strip()],
                }
        except (csv.Error, TypeError):
            continue
    return by_filename


def parse_standard_catalog_metadata(root: Path):
    """Read the standard master catalog and per-category provenance lists.

    The source corpus ships two complementary formats: one tab-separated
    searchable master catalog and one human-readable provenance list per
    category.  Both are indexed by the delivered PDF filename so no automatic
    topic classification is introduced.
    """
    by_filename = {}

    for path in root.rglob('01_全部标准检索目录.txt'):
        try:
            lines = path.read_text(encoding='utf-8-sig', errors='replace').splitlines()
        except OSError:
            continue
        header_index = next(
            (index for index, line in enumerate(lines) if line.startswith('分类\t标准号\t标准名称\t文件名')),
            None,
        )
        if header_index is None:
            continue
        for row in csv.DictReader(lines[header_index:], delimiter='\t'):
            filename = _normalized_filename(row.get('文件名'))
            if not filename:
                continue
            by_filename[filename] = {
                'title': (row.get('标准名称') or '').strip() or None,
                'standard_number': (row.get('标准号') or '').strip() or None,
                'standard_category': (row.get('分类') or '').strip() or None,
                'authority_status': 'unverified',
            }

    def commit(entry, category):
        filename = _normalized_filename(entry.get('文件'))
        if not filename:
            return
        existing = by_filename.setdefault(filename, {})
        numbered = entry.get('_numbered') or ''
        match = re.match(r'^(.+?)\s{2,}(.+?)\s*$', numbered)
        if match:
            existing['standard_number'] = match.group(1).strip()
            existing['title'] = match.group(2).strip()
        field_map = {
            '地区/行业': 'issuing_authority',
            '实施日期': 'publication_date',
            '来源目录状态': 'source_catalog_status',
            '来源页': 'source_url',
            '全文地址': 'download_url',
            'SHA256': 'expected_sha256',
            '类型': 'standard_type',
        }
        for source, target in field_map.items():
            value = str(entry.get(source) or '').strip()
            if value:
                existing[target] = value
        page_count = str(entry.get('PDF页数') or '').strip()
        if page_count.isdigit():
            existing['expected_page_count'] = int(page_count)
        existing['standard_category'] = category or existing.get('standard_category')
        existing['authority_status'] = 'unverified'

    for path in root.rglob('00_标准清单与下载来源.txt'):
        category = path.parent.name
        try:
            lines = path.read_text(encoding='utf-8-sig', errors='replace').splitlines()
        except OSError:
            continue
        entry = {}
        for raw_line in lines:
            line = raw_line.strip()
            numbered = re.match(r'^\d+[.．]\s*(.+)$', line)
            if numbered:
                commit(entry, category)
                entry = {'_numbered': numbered.group(1).strip()}
                continue
            if '：' in line and entry:
                key, value = line.split('：', 1)
                entry[key.strip()] = value.strip()
        commit(entry, category)

    return by_filename


def infer_document_kind(relative_path: str):
    lowered = relative_path.lower()
    if any(word in lowered for word in ('标准', 'standard', '规范')):
        return 'standard'
    if any(word in lowered for word in ('政策', '通知', '意见稿', 'policy')):
        return 'policy'
    if any(word in lowered for word in ('指南', '方法', '规程', 'guideline', 'method')):
        return 'method_guideline'
    return 'academic_paper'


def build_manifest(source_root, domain_mapping):
    root = Path(source_root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError('source_root 不存在或不是目录')
    ris = parse_ris_metadata(root)
    txt = parse_tabular_txt_metadata(root)
    standards = parse_standard_catalog_metadata(root)
    metadata_index = {**txt, **standards, **ris}
    rows = []
    for path in sorted(
        (item for item in root.rglob('*') if item.is_file() and item.suffix.lower() in BODY_SUFFIXES),
        key=lambda item: item.as_posix().lower(),
    ):
        relative = path.relative_to(root).as_posix()
        source_category = relative.split('/', 1)[0] if '/' in relative else 'uncategorized'
        labels = domain_mapping.get(source_category) or []
        if isinstance(labels, str):
            labels = [labels]
        metadata = metadata_index.get(path.name.lower(), {})
        row = {
            'schema_version': '1.0',
            'item_key': _stable_item_key(relative),
            'path': relative,
            'document_kind': infer_document_kind(relative),
            'title': metadata.get('title') or path.stem,
            'authors': metadata.get('authors') or [],
            'doi': metadata.get('doi'),
            'journal': metadata.get('journal'),
            'publication_date': metadata.get('publication_date'),
            'standard_number': metadata.get('standard_number'),
            'issuing_authority': metadata.get('issuing_authority'),
            'authority_status': metadata.get('authority_status'),
            'source_category': source_category,
            'cross_categories': [],
            'domain_labels': labels,
        }
        source_metadata = {
            key: metadata[key]
            for key in (
                'standard_category', 'standard_type', 'source_catalog_status',
                'source_url', 'download_url', 'expected_sha256',
                'expected_page_count',
            )
            if metadata.get(key) is not None
        }
        if source_metadata:
            row['source_metadata'] = source_metadata
        rows.append(row)
    return rows


def load_domain_mapping(path):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise ValueError('domain mapping 必须是 JSON 对象')
    return data

"""Manifest-driven administrator ingestion for literature corpora."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import uuid
import zipfile
from datetime import datetime, UTC
from pathlib import Path, PurePosixPath

from framework.config import Config
from framework.knowledge.taxonomy import DOMAIN_CODES, normalize_label_codes
from framework.models.document import Document
from framework.models.document_label import DocumentLabel
from framework.models.ingestion import IngestionBatch, IngestionItem
from framework.models.user import db
from framework.upload import ingestion_worker
from framework.upload.document_parser import caj_converter_is_available
from framework.upload.file_upload import (
    allowed_file, compute_file_hash, get_file_type, validate_file_content,
)


MAX_ARCHIVE_ENTRIES = 5000
MAX_ARCHIVE_UNCOMPRESSED = 5 * 1024 * 1024 * 1024
MAX_ARCHIVE_RATIO = 100


class BatchValidationError(ValueError):
    pass


def configured_staging_roots():
    try:
        raw = json.loads(Config.LITERATURE_STAGING_ROOTS_JSON or '{}')
    except json.JSONDecodeError as exc:
        raise BatchValidationError('LITERATURE_STAGING_ROOTS_JSON 不是合法 JSON') from exc
    if not isinstance(raw, dict):
        raise BatchValidationError('LITERATURE_STAGING_ROOTS_JSON 必须是对象')
    roots = {}
    for token, value in raw.items():
        root = Path(str(value)).expanduser().resolve()
        if not root.is_dir():
            continue
        roots[str(token)] = root
    return roots


def resolve_staging_root(token):
    root = configured_staging_roots().get(str(token))
    if root is None:
        raise BatchValidationError('未知或不可用的 staging token')
    return root


def _safe_relative(root: Path, relative_value: str) -> Path:
    relative = Path(str(relative_value))
    if relative.is_absolute():
        raise BatchValidationError('manifest 只能使用相对路径')
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise BatchValidationError('manifest 路径越过 staging root') from exc
    return resolved


def _read_manifest(root: Path, manifest_relative_path: str):
    path = _safe_relative(root, manifest_relative_path)
    if not path.is_file():
        raise BatchValidationError('manifest 文件不存在')
    payload = path.read_bytes()
    rows = []
    for line_no, raw_line in enumerate(payload.decode('utf-8-sig').splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise BatchValidationError(f'manifest 第 {line_no} 行不是合法 JSON') from exc
        if not isinstance(row, dict):
            raise BatchValidationError(f'manifest 第 {line_no} 行必须是对象')
        row['_line_no'] = line_no
        rows.append(row)
    return path, hashlib.sha256(payload).hexdigest(), rows


def _normalized_zip_name(info: zipfile.ZipInfo):
    name = info.filename
    if not (info.flag_bits & 0x800):
        try:
            name = name.encode('cp437').decode('gbk')
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return name.replace('\\', '/')


def _validate_zip_entry(info: zipfile.ZipInfo, name: str):
    path = PurePosixPath(name)
    if (
        path.is_absolute() or '..' in path.parts
        or re.match(r'^[A-Za-z]:', name) or name.startswith('//')
    ):
        raise BatchValidationError(f'ZIP 条目路径不安全: {name}')
    reserved = {
        'CON', 'PRN', 'AUX', 'NUL',
        *(f'COM{i}' for i in range(1, 10)),
        *(f'LPT{i}' for i in range(1, 10)),
    }
    if any(part.split('.')[0].upper() in reserved for part in path.parts):
        raise BatchValidationError(f'ZIP 条目使用保留设备名: {name}')
    mode = info.external_attr >> 16
    if mode and stat.S_ISLNK(mode):
        raise BatchValidationError(f'ZIP 不允许符号链接: {name}')
    if info.file_size and not info.compress_size:
        raise BatchValidationError(f'ZIP 条目压缩比异常: {name}')
    if info.compress_size and info.file_size / info.compress_size > MAX_ARCHIVE_RATIO:
        raise BatchValidationError(f'ZIP 条目压缩比超限: {name}')


def _iter_manifest_sources(root: Path, row: dict):
    relative_path = str(row.get('path') or '').strip()
    if not relative_path:
        raise BatchValidationError('manifest item 缺少 path')
    source = _safe_relative(root, relative_path)
    display_relative = relative_path.replace('\\', '/')
    if not source.is_file():
        raise BatchValidationError(f'源文件不存在: {relative_path}')
    if source.suffix.lower() != '.zip':
        if source.suffix.lower() not in {'.pdf', '.caj'}:
            raise BatchValidationError('批次正文仅支持 PDF/CAJ；目录、清单和辅助文件不得入库')
        yield {
            'display_path': display_relative,
            'source_path': source,
            'archive_entry': None,
        }
        return

    with zipfile.ZipFile(source) as archive:
        infos = [item for item in archive.infolist() if not item.is_dir()]
        if len(infos) > MAX_ARCHIVE_ENTRIES:
            raise BatchValidationError('ZIP 条目数超限')
        if sum(item.file_size for item in infos) > MAX_ARCHIVE_UNCOMPRESSED:
            raise BatchValidationError('ZIP 总解压大小超限')
        for info in infos:
            name = _normalized_zip_name(info)
            _validate_zip_entry(info, name)
            if not allowed_file(name) or name.lower().endswith(
                ('.txt', '.md', '.csv', '.dat', '.xlsx', '.xls', '.docx')
            ):
                continue
            yield {
                'display_path': f"{display_relative}!{name}",
                'source_path': source,
                'archive_entry': info.filename,
                'normalized_entry': name,
            }


def _materialize_source(source, destination: Path):
    if source.get('archive_entry') is None:
        shutil.copyfile(source['source_path'], destination)
        return
    with zipfile.ZipFile(source['source_path']) as archive:
        with archive.open(source['archive_entry']) as input_stream:
            with destination.open('wb') as output_stream:
                shutil.copyfileobj(input_stream, output_stream)


def _validate_labels(row):
    labels = normalize_label_codes(row.get('domain_labels') or [])
    labels = [label for label in labels if label in DOMAIN_CODES]
    if not labels:
        raise BatchValidationError('item 必须提供至少一个有效一级领域标签')
    return labels


def _submit_job(document, item, file_path, labels):
    try:
        ingestion_worker.submit_ingest(
            document_id=document.id,
            file_path=file_path,
            file_type=document.file_type,
            doc_name=document.doc_name,
            category=document.category,
            treatment_type=document.treatment_type,
            owner_id=document.create_by,
            visibility_scope='public',
            domain_labels=labels,
            ingestion_item_id=item.id,
        )
        return True
    except ingestion_worker.QueueCapacityExceeded:
        document.status = Document.STATUS_FAILED
        document.processing_stage = 'failed'
        document.failure_code = 'queue_capacity_exceeded'
        document.failure_message = '文献入库队列已满，请稍后重试'
        document.retryable = True
        item.state = 'failed'
        item.stage = 'failed'
        item.failure_code = 'queue_capacity_exceeded'
        item.failure_message = document.failure_message
        item.retryable = True
        item.finished_at = datetime.now(UTC)
        return False


def _normalize_doi(value):
    doi = str(value or '').strip().lower()
    doi = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', doi)
    doi = re.sub(r'^doi:\s*', '', doi)
    return doi or None


def _normalize_standard(value):
    return re.sub(r'\s+', '', str(value or '')).upper() or None


def _title_review_key(row):
    title = re.sub(r'\W+', '', str(row.get('title') or '')).lower()
    year = str(row.get('publication_date') or '')[:4]
    authors = row.get('authors') or []
    first_author = str(authors[0] if authors else '').strip().lower()
    return (title, year, first_author) if title else None


def preflight_manifest(staging_token, manifest_relative_path):
    root = resolve_staging_root(staging_token)
    _, manifest_hash, rows = _read_manifest(root, manifest_relative_path)
    results = []
    seen_hashes = {}
    seen_dois = {}
    seen_standards = {}
    seen_titles = {}
    for row_index, row in enumerate(rows, start=1):
        base_key = str(row.get('item_key') or f'line-{row["_line_no"]}')
        try:
            if str(row.get('schema_version') or '') != '1.0':
                raise BatchValidationError('schema_version 必须为 1.0')
            labels = _validate_labels(row)
            sources = list(_iter_manifest_sources(root, row))
            if not sources:
                raise BatchValidationError('item 没有可入库的 PDF/CAJ 文件')
        except (BatchValidationError, ValueError, zipfile.BadZipFile) as exc:
            results.append({
                'item_key': base_key,
                'path': str(row.get('path') or ''),
                'state': 'invalid',
                'reason': str(exc),
            })
            continue

        for source_index, source in enumerate(sources, start=1):
            display_path = source['display_path']
            suffix = Path(source.get('normalized_entry') or display_path).suffix.lower()
            item_key = base_key if len(sources) == 1 else f'{base_key}:{source_index}'
            source_row = dict(row)
            if source.get('archive_entry') is not None:
                # A ZIP manifest row represents several independent documents.
                # Its container title must not make every archive entry look like
                # the same title/year/author candidate.
                source_row['title'] = Path(
                    source.get('normalized_entry') or source['archive_entry']
                ).stem
            try:
                with tempfile.TemporaryDirectory(prefix='literature_preflight_') as temp_dir:
                    temp_path = Path(temp_dir) / f'candidate{suffix}'
                    _materialize_source(source, temp_path)
                    if temp_path.stat().st_size > Config.MAX_CONTENT_LENGTH:
                        raise BatchValidationError('文件大小超过允许上限')
                    file_type = get_file_type(temp_path.name)
                    validate_file_content(str(temp_path), file_type)
                    digest = compute_file_hash(str(temp_path))
                    with temp_path.open('rb') as stream:
                        caj_is_pdf = file_type == 'caj' and stream.read(5) == b'%PDF-'
                if file_type == 'caj' and not caj_is_pdf and not caj_converter_is_available(
                    Config.CAJ_CONVERTER_PATH
                ):
                    state, reason = 'processor_unavailable', 'CAJ 转换器不可用'
                elif digest in seen_hashes:
                    state, reason = 'duplicate', f'与 {seen_hashes[digest]} 内容相同'
                else:
                    state, reason = 'ready', None
                    seen_hashes[digest] = item_key
                doi = _normalize_doi(source_row.get('doi'))
                standard_key = (
                    _normalize_standard(source_row.get('standard_number')),
                    str(source_row.get('issuing_authority') or '').strip().lower(),
                )
                title_key = _title_review_key(source_row)
                if state == 'ready' and doi and doi in seen_dois:
                    state, reason = 'duplicate', f'与 {seen_dois[doi]} DOI 相同'
                elif state == 'ready' and standard_key[0] and standard_key in seen_standards:
                    state, reason = 'duplicate', f'与 {seen_standards[standard_key]} 标准号相同'
                elif state == 'ready' and title_key and title_key in seen_titles:
                    state, reason = 'needs_review', f'与 {seen_titles[title_key]} 标题候选重复'
                existing_doc = None
                if state == 'ready':
                    existing_doc = Document.query.filter_by(
                        file_hash=digest,
                        status=Document.STATUS_COMPLETED,
                        visibility_scope='public',
                    ).first()
                if state == 'ready' and not existing_doc and doi:
                    existing_doc = Document.query.filter_by(
                        doi_normalized=doi,
                        status=Document.STATUS_COMPLETED,
                        visibility_scope='public',
                    ).first()
                if state == 'ready' and not existing_doc and standard_key[0]:
                    existing_doc = Document.query.filter_by(
                        standard_number_normalized=standard_key[0],
                        issuing_authority=source_row.get('issuing_authority'),
                        status=Document.STATUS_COMPLETED,
                        visibility_scope='public',
                    ).first()
                if existing_doc:
                    state = 'duplicate'
                    reason = f'与公共文档 {existing_doc.id} 重复'
                if state == 'ready':
                    if doi:
                        seen_dois[doi] = item_key
                    if standard_key[0]:
                        seen_standards[standard_key] = item_key
                    if title_key:
                        seen_titles[title_key] = item_key
                results.append({
                    'item_key': item_key,
                    'path': display_path,
                    'state': state,
                    'reason': reason,
                    'sha256': digest,
                    'file_type': file_type,
                    'domain_labels': labels,
                    'document_kind': source_row.get('document_kind', 'other'),
                    '_source': source,
                    '_row': source_row,
                })
            except Exception as exc:
                results.append({
                    'item_key': item_key,
                    'path': display_path,
                    'state': 'invalid',
                    'reason': str(exc),
                })
    counts = {}
    for result in results:
        counts[result['state']] = counts.get(result['state'], 0) + 1
    public_items = [
        {key: value for key, value in item.items() if not key.startswith('_')}
        for item in results
    ]
    processor_health = {
        'caj_converter': caj_converter_is_available(Config.CAJ_CONVERTER_PATH),
        'poppler': bool(shutil.which('pdftoppm') or shutil.which('pdftoppm.exe')),
        'tesseract': bool(shutil.which('tesseract') or shutil.which('tesseract.exe')),
        'tesseract_chi_sim': False,
    }
    if processor_health['tesseract']:
        try:
            import pytesseract
            processor_health['tesseract_chi_sim'] = 'chi_sim' in pytesseract.get_languages()
        except Exception:
            pass
    return {
        'manifest_hash': manifest_hash,
        'total': len(results),
        'counts': counts,
        'processor_health': processor_health,
        'items': public_items,
    }, results


def execute_manifest(*, staging_token, manifest_relative_path, batch_key, name, actor_id):
    report, internal_items = preflight_manifest(staging_token, manifest_relative_path)
    existing = IngestionBatch.query.filter_by(batch_key=batch_key).first()
    if existing:
        if existing.manifest_hash == report['manifest_hash']:
            return existing, False
        raise BatchValidationError('相同 batch_key 已对应不同 manifest')

    batch = IngestionBatch(
        batch_key=batch_key,
        name=name,
        source_type='manifest',
        state='processing',
        dry_run=False,
        requested_by=actor_id,
        manifest_hash=report['manifest_hash'],
        source_artifact_id=f'{staging_token}:{manifest_relative_path}',
        total_count=report['total'],
        config_snapshot={
            'retain_derived_pdf': Config.LITERATURE_RETAIN_DERIVED_PDF,
        },
        summary=report,
        started_at=datetime.now(UTC),
    )
    db.session.add(batch)
    db.session.flush()
    jobs = []
    os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

    for candidate in internal_items:
        state = candidate['state']
        if state != 'ready':
            item = IngestionItem(
                batch_id=batch.id,
                attempt_no=1,
                source_relative_path=candidate.get('path'),
                source_hash=candidate.get('sha256'),
                idempotency_key=candidate.get('item_key'),
                state='skipped_duplicate' if state == 'duplicate' else state,
                stage='skipped_duplicate' if state == 'duplicate' else state,
                progress=100,
                review_status='approved',
                submitted_domain_labels=candidate.get('domain_labels') or [],
                approved_domain_labels=candidate.get('domain_labels') or [],
                failure_code=None if state == 'duplicate' else state,
                failure_message=candidate.get('reason'),
                retryable=state == 'processor_unavailable',
                config_snapshot=batch.config_snapshot,
                finished_at=datetime.now(UTC),
            )
            db.session.add(item)
            continue

        row = candidate['_row']
        suffix = Path(candidate.get('_source', {}).get('normalized_entry') or candidate['path']).suffix.lower()
        new_filename = f'{uuid.uuid4().hex}{suffix}'
        file_path = Path(Config.UPLOAD_FOLDER) / new_filename
        _materialize_source(candidate['_source'], file_path)
        existing_doc = Document.query.filter_by(
            file_hash=candidate['sha256'],
            status=Document.STATUS_COMPLETED,
            visibility_scope='public',
        ).first()
        if not existing_doc and _normalize_doi(row.get('doi')):
            existing_doc = Document.query.filter_by(
                doi_normalized=_normalize_doi(row.get('doi')),
                status=Document.STATUS_COMPLETED,
                visibility_scope='public',
            ).first()
        if not existing_doc and _normalize_standard(row.get('standard_number')):
            existing_doc = Document.query.filter_by(
                standard_number_normalized=_normalize_standard(row.get('standard_number')),
                issuing_authority=row.get('issuing_authority'),
                status=Document.STATUS_COMPLETED,
                visibility_scope='public',
            ).first()
        if existing_doc:
            file_path.unlink(missing_ok=True)
            db.session.add(IngestionItem(
                batch_id=batch.id,
                attempt_no=1,
                source_relative_path=candidate['path'],
                source_hash=candidate['sha256'],
                idempotency_key=candidate['item_key'],
                state='skipped_duplicate', stage='skipped_duplicate', progress=100,
                review_status='approved',
                approved_domain_labels=candidate['domain_labels'],
                quality_summary={'canonical_document_id': existing_doc.id},
                config_snapshot=batch.config_snapshot,
                finished_at=datetime.now(UTC),
            ))
            continue

        document = Document(
            doc_name=Path(candidate['path']).name,
            file_path=new_filename,
            file_type=candidate['file_type'],
            file_size=file_path.stat().st_size,
            file_hash=candidate['sha256'],
            status=Document.STATUS_PENDING,
            category=row.get('category', 'other'),
            treatment_type=row.get('treatment_type'),
            visibility_scope='private',
            document_kind=candidate['document_kind'],
            title=row.get('title'),
            language=row.get('language'),
            doi_normalized=_normalize_doi(row.get('doi')),
            standard_number_normalized=_normalize_standard(row.get('standard_number')),
            issuing_authority=row.get('issuing_authority'),
            authority_status=(
                row.get('authority_status')
                if row.get('authority_status') in {'unverified', 'draft'}
                else 'unverified'
            ),
            bibliographic_metadata={
                'authors': row.get('authors') or [],
                'journal': row.get('journal'),
                'publication_date': row.get('publication_date'),
            },
            provenance_metadata={
                'source_category': row.get('source_category'),
                'cross_categories': row.get('cross_categories') or [],
                'original_relative_path': candidate['path'],
                'source_metadata': row.get('source_metadata') or {},
            },
            processing_stage='accepted',
            review_status=Document.REVIEW_APPROVED,
            reviewed_by=actor_id,
            reviewed_at=datetime.now(UTC),
            create_by=actor_id,
        )
        db.session.add(document)
        db.session.flush()
        for code in candidate['domain_labels']:
            label = DocumentLabel(
                document_id=document.id,
                label_code=code,
                label_level='domain',
                review_status=DocumentLabel.STATUS_APPROVED,
                assignment_source=DocumentLabel.SOURCE_MANUAL,
                create_by=actor_id,
                review_by=actor_id,
                review_time=datetime.now(UTC),
            )
            db.session.add(label)
        item = IngestionItem(
            batch_id=batch.id,
            document_id=document.id,
            attempt_no=1,
            source_relative_path=candidate['path'],
            source_hash=candidate['sha256'],
            idempotency_key=candidate['item_key'],
            state='pending', stage='accepted', progress=0,
            review_status='approved',
            submitted_domain_labels=candidate['domain_labels'],
            approved_domain_labels=candidate['domain_labels'],
            reviewed_by=actor_id,
            reviewed_at=datetime.now(UTC),
            config_snapshot=batch.config_snapshot,
        )
        db.session.add(item)
        db.session.flush()
        jobs.append((document, item, str(file_path), candidate['domain_labels']))

    db.session.flush()
    refresh_batch_counters(batch.id)
    db.session.commit()
    for document, item, file_path, labels in jobs:
        _submit_job(document, item, file_path, labels)
    if jobs:
        db.session.flush()
        refresh_batch_counters(batch.id)
        db.session.commit()
    return batch, True


def refresh_batch_counters(batch_id):
    if not batch_id:
        return None
    batch = db.session.get(IngestionBatch, batch_id)
    if not batch:
        return None
    effective_items = []
    latest_by_document = {}
    for item in batch.items:
        if item.document_id is None:
            effective_items.append(item)
            continue
        current = latest_by_document.get(item.document_id)
        if current is None or (item.attempt_no, item.id) > (
            current.attempt_no, current.id,
        ):
            latest_by_document[item.document_id] = item
    effective_items.extend(latest_by_document.values())
    states = [item.state for item in effective_items]
    batch.completed_count = states.count('completed')
    batch.failed_count = sum(state in {'failed', 'invalid', 'processor_unavailable'} for state in states)
    batch.skipped_count = states.count('skipped_duplicate')
    batch.review_count = states.count('needs_review')
    batch.cancelled_count = states.count('cancelled')
    terminal = {
        'completed', 'failed', 'invalid', 'processor_unavailable',
        'skipped_duplicate', 'needs_review', 'cancelled', 'rejected',
        'superseded',
    }
    if states and all(state in terminal for state in states):
        batch.finished_at = datetime.now(UTC)
        if batch.failed_count:
            batch.state = 'partial_success' if batch.completed_count else 'failed'
        elif batch.cancelled_count:
            batch.state = 'cancelled'
        else:
            batch.state = 'completed'
    return batch


def resume_batch(batch_key):
    """Resume the latest unfinished attempt for each document in a batch."""
    batch = IngestionBatch.query.filter_by(batch_key=batch_key).first()
    if not batch:
        raise BatchValidationError('批次不存在')
    latest_by_document = {}
    for item in batch.items:
        if item.document_id is None:
            continue
        current = latest_by_document.get(item.document_id)
        if current is None or item.attempt_no > current.attempt_no:
            latest_by_document[item.document_id] = item

    jobs = []
    for previous in latest_by_document.values():
        if previous.state not in {'pending', 'processing', 'failed'}:
            continue
        if previous.state == 'failed' and not previous.retryable:
            continue
        document = previous.document
        if not document or document.review_status != Document.REVIEW_APPROVED:
            continue
        if previous.state == 'pending':
            item = previous
        else:
            previous.state = 'superseded'
            previous.stage = 'superseded'
            previous.progress = 100
            previous.finished_at = datetime.now(UTC)
            item = IngestionItem(
                batch_id=batch.id,
                document_id=document.id,
                attempt_no=previous.attempt_no + 1,
                source_relative_path=previous.source_relative_path,
                source_hash=previous.source_hash,
                idempotency_key=previous.idempotency_key,
                review_status='approved',
                submitted_domain_labels=previous.submitted_domain_labels,
                approved_domain_labels=previous.approved_domain_labels,
                reviewed_by=previous.reviewed_by,
                reviewed_at=previous.reviewed_at,
                config_snapshot=batch.config_snapshot,
            )
            db.session.add(item)
            db.session.flush()
        item.state = 'pending'
        item.stage = 'accepted'
        item.progress = 0
        item.failure_code = None
        item.failure_message = None
        item.retryable = False
        item.started_at = None
        item.finished_at = None
        document.status = Document.STATUS_PENDING
        document.processing_stage = 'accepted'
        document.failure_code = None
        document.failure_message = None
        document.retryable = False
        jobs.append((document, item))

    if not jobs:
        raise BatchValidationError('批次中没有可恢复项目')
    batch.state = 'processing'
    batch.finished_at = None
    db.session.commit()
    for document, item in jobs:
        _submit_job(
            document, item,
            str(Path(Config.UPLOAD_FOLDER) / document.file_path),
            item.approved_domain_labels or [],
        )
    db.session.flush()
    refresh_batch_counters(batch.id)
    db.session.commit()
    return batch, len(jobs)

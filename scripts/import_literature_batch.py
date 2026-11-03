"""Preflight or execute a registered literature manifest batch."""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / '.env')


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--staging-token')
    source.add_argument('--source-root')
    parser.add_argument('--manifest', help='Path relative to the registered root')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--batch-key')
    parser.add_argument('--name')
    parser.add_argument('--actor-id', type=int)
    parser.add_argument('--report-output', help='Write the full JSON result to this path')
    parser.add_argument('--summary-only', action='store_true')
    return parser


def _emit(payload, args):
    if args.report_output:
        output = Path(args.report_output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8'
        )
    displayed = payload
    if args.summary_only and isinstance(payload, dict):
        displayed = copy.deepcopy(payload)
        displayed.pop('items', None)
        batch = displayed.get('batch')
        if isinstance(batch, dict):
            batch.pop('items', None)
            if isinstance(batch.get('summary'), dict):
                batch['summary'].pop('items', None)
        displayed['report_output'] = str(Path(args.report_output).resolve()) if args.report_output else None
    print(json.dumps(displayed, ensure_ascii=False, indent=2))


def main(argv=None):
    args = build_parser().parse_args(argv)
    if sum((args.dry_run, args.execute, args.resume)) != 1:
        raise SystemExit('Exactly one of --dry-run, --execute, or --resume is required')

    from framework.api.app import create_app
    from framework.config import Config
    from framework.upload.literature_batch import execute_manifest, preflight_manifest, resume_batch

    if args.resume:
        if not args.batch_key:
            raise SystemExit('--resume requires --batch-key')
        app = create_app()
        with app.app_context():
            batch, resumed = resume_batch(args.batch_key)
            _emit({
                'resumed': resumed,
                'batch': batch.to_dict(include_items=True),
            }, args)
        return 0

    if not args.manifest or not (args.staging_token or args.source_root):
        raise SystemExit('--dry-run/--execute require --manifest and a staging source')

    staging_token = args.staging_token
    if args.source_root:
        source_root = str(Path(args.source_root).expanduser().resolve())
        try:
            roots = json.loads(Config.LITERATURE_STAGING_ROOTS_JSON or '{}')
        except json.JSONDecodeError:
            roots = {}
        staging_token = '__cli_source_root__'
        roots[staging_token] = source_root
        Config.LITERATURE_STAGING_ROOTS_JSON = json.dumps(roots)

    app = create_app()
    with app.app_context():
        if args.dry_run:
            report, _ = preflight_manifest(staging_token, args.manifest)
            _emit(report, args)
            return 0
        if not args.batch_key or args.actor_id is None:
            raise SystemExit('--execute requires --batch-key and --actor-id')
        batch, created = execute_manifest(
            staging_token=staging_token,
            manifest_relative_path=args.manifest,
            batch_key=args.batch_key,
            name=args.name or args.batch_key,
            actor_id=args.actor_id,
        )
        _emit({
            'created': created,
            'batch': batch.to_dict(include_items=True),
        }, args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Generate a candidate literature JSONL manifest; never imports documents."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / '.env')

from framework.upload.manifest_builder import build_manifest, load_domain_mapping


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True)
    parser.add_argument('--domain-map', required=True, help='JSON map: source category -> domain labels')
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)

    rows = build_manifest(args.source_root, load_domain_mapping(args.domain_map))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', encoding='utf-8', newline='\n') as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    print(json.dumps({
        'output': str(output.resolve()),
        'count': len(rows),
        'missing_domain_mapping': sum(not row['domain_labels'] for row in rows),
    }, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Local cover OCR evidence, kept separate from frozen extractor input text."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
import json
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.rebuild_kg_extraction_benchmark import OUT,SOURCE,dump,readlines
from framework.knowledge_graph.benchmark_rebuild import sha256_file

DEST=OUT/'execution/cover-ocr-v1'
TESSERACT=Path('D:/soft/Tesseract-OCR/tesseract.exe')


def prepare(document):
    import fitz
    path=DEST/(str(document['id'])+'.json')
    if path.exists():return json.loads(path.read_text(encoding='utf-8'))
    original=next((SOURCE/p for p in document['source_paths'] if (SOURCE/p).is_file()),None)
    if original is None or sha256_file(original)!=document['file_hash']:raise ValueError('source_file_hash_mismatch')
    pages=[]
    with fitz.open(original) as pdf:
        for index in range(min(2,len(pdf))):
            image=DEST/f"{document['id']}-page{index+1}.png"
            pdf[index].get_pixmap(dpi=180,alpha=False).save(image)
            result=subprocess.run([str(TESSERACT),str(image),'stdout','-l','chi_sim+eng','--psm','3'],
                capture_output=True,timeout=90,check=True)
            text=result.stdout.decode('utf-8')
            text_path=image.with_suffix('.txt');text_path.write_text(text,encoding='utf-8')
            pages.append(dict(page=index+1,text=text,image_path=image.relative_to(ROOT).as_posix(),
                image_sha256=sha256_file(image),ocr_text_path=text_path.relative_to(ROOT).as_posix(),
                ocr_text_sha256=sha256_file(text_path),dpi=180,language='chi_sim+eng',psm=3,
                evidence_channel='local_ocr_from_pdf_render_not_extractor_input'))
    row=dict(document_id=document['id'],file_sha256=document['file_hash'],pages=pages,
        input_chunks_modified=False,identity_verified=False,requires_identifier_crosscheck=True,
        generated_at=datetime.now(timezone.utc).isoformat())
    dump(path,row);return row


def main(limit=None):
    packets=readlines(OUT/'metadata-review-preparation/source-packets.jsonl')
    wanted={p['document_id'] for p in packets if p['visual_review_required_if_no_readable_pdf_identity']}
    for p in (OUT/'execution/metadata-audit/items.jsonl').read_text(encoding='utf-8').splitlines():
        r=json.loads(p)
        if r['metadata'].get('identity_status')=='requires_visual':wanted.add(r['document_id'])
    documents=[d for d in readlines(OUT/'execution/source-review-r1/document-pool-refined.jsonl') if d['id'] in wanted]
    DEST.mkdir(parents=True,exist_ok=True)
    config=dict(document_ids=[d['id'] for d in documents],dpi=180,languages='chi_sim+eng',psm=3,
        tesseract_binary_sha256=sha256_file(TESSERACT),script_sha256=sha256_file(Path(__file__)),
        original_input_unchanged=True,local_only=True,cloud_requests=0)
    manifest=DEST/'run-config.json'
    if manifest.exists() and json.loads(manifest.read_text(encoding='utf-8'))!=config:raise ValueError('ocr_run_frozen')
    if not manifest.exists():dump(manifest,config)
    selected=documents if limit is None else documents[:limit]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(prepare,d):d['id'] for d in selected}
        for future in as_completed(futures):
            row=future.result();print(json.dumps(dict(document_id=row['document_id'],pages=len(row['pages']))),flush=True)
    dump(DEST/'progress.json',dict(target_documents=len(documents),saved_documents=len(list(DEST.glob('[0-9]*.json'))),
        cloud_requests=0,extractor_inputs_modified=False,active=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--limit',type=int);args=parser.parse_args();main(args.limit)

"""Add a historical-use notice to the mutable legacy UI, preserving its bytes."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]/"artifacts/knowledge_platform"


def main():
    old=ROOT/"extraction-benchmark-v2/dataset-v1/review.html"
    external=ROOT/"external-benchmark-v1"
    original=old.read_bytes()
    if b'external-benchmark-history-notice' in original:
        print('Historical notice already present; no changes.');return
    checksum=hashlib.sha256(original).hexdigest()
    base=ROOT/"extraction-benchmark-v2"
    for manifest in set(base.rglob('*manifest*.json'))|set(base.rglob('*freeze*.json')):
        if checksum in manifest.read_text(encoding='utf-8'):
            raise ValueError('legacy_review_is_frozen_do_not_modify:'+str(manifest))
    backup=external/"governance/internal-review-before-external-transition.html"
    backup.parent.mkdir(parents=True,exist_ok=True)
    if backup.exists() and backup.read_bytes()!=original:raise ValueError('historical_UI_backup_already_differs')
    backup.write_bytes(original)
    text=original.decode('utf-8')
    marker='<h1>'
    position=text.find(marker)
    if position<0:raise ValueError('legacy_UI_heading_missing')
    notice='<div id="external-benchmark-history-notice" style="padding:20px;background:#fff0c9;border:2px solid #b97c00"><strong>历史诊断资产：此页保留原内部500条输入与旧参考状态。</strong>当前主评测已转向外部公开数据，旧参考不再作为正式验收依据。<a href="../../external-benchmark-v1/review.html">打开当前外部评测审核页</a></div>'
    updated=text[:position]+notice+text[position:]
    assert updated.replace(notice,'',1).encode('utf-8')==original
    old.write_bytes(updated.encode('utf-8'))
    record={'scope':'mutable_historical_UI_notice_only','original_sha256':checksum,'updated_sha256':hashlib.sha256(old.read_bytes()).hexdigest(),
            'backup':str(backup.relative_to(external)),'frozen_inputs_labels_and_masks_changed':False,
            'frozen_manifest_matches_before_change':0,'target':'../../external-benchmark-v1/review.html'}
    (external/'governance/internal-review-transition.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(record))


if __name__=='__main__':main()

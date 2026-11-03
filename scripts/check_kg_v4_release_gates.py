"""Fail closed: new corpus expansion/experiments require completed calibration."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import write
from framework.knowledge_graph.evaluation_v4_scoring import release_gates
BASE=ROOT/'artifacts/knowledge_platform/gold-v4'

def main():
    path=BASE/'calibration/agreement-report.json'
    if not path.exists():path=BASE/'calibration/agreement-report-pilot.json'
    calibration=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    verification=BASE/'scorer-verification.json'
    verified=json.loads(verification.read_text(encoding='utf-8')).get('passed',False) if verification.exists() else False
    result=release_gates(calibration,verified)
    result['gate_scope']='historical paired automatic-annotation qualification; not direct-source silver adjudication'
    write(BASE/'release-gates.json',result)
    print(json.dumps(result))
    return 0 if result['allow_model_experiment'] else 2

if __name__=='__main__':raise SystemExit(main())

"""User-requested original-ten diagnostic despite failed controls; never opens release gates."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.experiment_kg_recall import read,write,jsonl,sha
from scripts.calibrate_kg_v4_r4 import BASE,OUT,identity
from framework.knowledge_graph.evaluation_v4 import input_digest,digest
from framework.knowledge_graph.annotation_tasks_r4 import annotate

async def main(arm):
    from dotenv import load_dotenv
    from openai import AsyncOpenAI
    import httpx
    load_dotenv(ROOT/'.env')
    parent=json.loads((OUT/'controls/gate.json').read_text(encoding='utf-8'))
    model=os.environ.get('SILICONFLOW_CHAT_MODEL','deepseek-ai/DeepSeek-V4-Flash');protocol=identity(model)
    if digest(json.dumps(protocol,sort_keys=True))!=parent['config_sha256']:raise ValueError('protocol_changed_since_controls')
    original=json.loads((BASE/'manifest.json').read_text(encoding='utf-8'))
    if sha(BASE/'calibration/inputs.jsonl')!=original['calibration_inputs_sha256']:raise ValueError('calibration_source_changed')
    if sha(BASE/'calibration'/('annotator-'+arm+'.jsonl'))!=sha(BASE/'calibration/inputs.jsonl'):raise ValueError('arm_source_changed')
    config=dict(kind='diagnostic_only_not_release_pilot',arm=arm,protocol=protocol,parent_controls_passed=parent['passed'],
        controls_sha256=sha(OUT/'controls/gate.json'),inputs_sha256=sha(BASE/'calibration/inputs.jsonl'),
        runner_sha256=sha(Path(__file__)),attempts_per_task=1,maximum_documents=10,maximum_requests=40,
        authorization='user explicitly requested new controls and original ten documents',
        gate_deviation='controls failed; original-ten run is diagnostic only, cannot satisfy qualification or authorize 90-row expansion')
    directory=OUT/('diagnostic-'+arm);directory.mkdir(exist_ok=True);path=directory/'config.json'
    if path.exists() and json.loads(path.read_text(encoding='utf-8'))!=config:raise ValueError('immutable_diagnostic_config_changed')
    write(path,config);config_sha=digest(json.dumps(config,sort_keys=True))
    rows=read(BASE/'calibration/inputs.jsonl')[:10];records=[];sem=asyncio.Semaphore(2)
    client=AsyncOpenAI(api_key=os.environ.get('KG_EXTRACTION_API_KEY') or os.environ['SILICONFLOW_API_KEY'],base_url=protocol['endpoint'],max_retries=0,timeout=65,
        http_client=httpx.AsyncClient(trust_env=False,follow_redirects=False))
    async def one(row):
        async with sem:
            path=directory/(input_digest(row)+'.json')
            if path.exists():
                result=json.loads(path.read_text(encoding='utf-8'))
                if result['config_sha256']!=config_sha or result['input_sha256']!=input_digest(row):raise ValueError('stale_diagnostic_cache')
            else:
                async def create(**kwargs):return await asyncio.wait_for(client.chat.completions.create(model=model,temperature=0,extra_body={'enable_thinking':False},**kwargs),timeout=60)
                result=await annotate(row,create,attempts=1);result.update(config_sha256=config_sha,diagnostic_only=True)
                write(path,result)
            records.append(result);write(directory/'progress.json',dict(target=10,completed=len(records),full_valid=sum(r['state']=='completed' for r in records),
                partial=sum(r['state']=='partial' for r in records),failed=sum(r['state']=='failed' for r in records)))
            print(json.dumps(dict(arm=arm,sample_id=row['sample_id'],state=result['state'],tasks=result['task_status'])),flush=True)
    try:await asyncio.gather(*(one(row) for row in rows))
    finally:await client.close()
    jsonl(directory/'responses.jsonl',sorted(records,key=lambda r:r['sample_id']))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['A','B'],required=True);args=p.parse_args();asyncio.run(main(args.arm))

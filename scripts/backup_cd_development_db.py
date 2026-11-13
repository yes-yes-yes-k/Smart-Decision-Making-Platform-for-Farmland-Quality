"""Create and verify a local PostgreSQL custom backup without exposing secrets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from dotenv import load_dotenv


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--env-file',required=True)
    parser.add_argument('--database',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--pg-bin',default='D:/soft/PostgreSQL/bin')
    args=parser.parse_args()
    load_dotenv(args.env_file)
    env=os.environ.copy()
    env['PGPASSWORD']=os.environ['DB_PASSWORD']
    path=Path(args.output); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as output:
        subprocess.run([str(Path(args.pg_bin)/'pg_dump.exe'),'-Fc','-h',os.getenv('DB_HOST','localhost'),
                        '-p',os.getenv('DB_PORT','5432'),'-U',os.getenv('DB_USER','postgres'),'-d',args.database],
                       env=env,stdout=output,check=True)
    subprocess.run([str(Path(args.pg_bin)/'pg_restore.exe'),'--list',str(path)],stdout=subprocess.DEVNULL,check=True)
    digest=hashlib.sha256()
    with path.open('rb') as data:
        for block in iter(lambda:data.read(1024*1024),b''):
            digest.update(block)
    result={'database':args.database,'file':path.name,'bytes':path.stat().st_size,'sha256':digest.hexdigest(),'archive_list_verified':True}
    path.with_suffix('.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    main()

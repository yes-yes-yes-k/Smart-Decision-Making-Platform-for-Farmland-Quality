"""Durable request reservations; unknown usage is never free. No credentials stored."""
import json
import sqlite3
import time
from pathlib import Path

class BudgetStop(RuntimeError):pass

class Budget:
    def __init__(self,path,*,total=10_000_000,stability=1_000_000,requests=5000):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.total,self.stability,self.requests=total,stability,requests
        with self.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY, phase TEXT, job TEXT, reserved INTEGER, charged INTEGER, state TEXT, error TEXT, created REAL, finished REAL)')
    def connect(self):return sqlite3.connect(self.path,timeout=10)
    def reserve(self,phase,job,options):
        reserved=len(json.dumps(options,ensure_ascii=False).encode('utf-8'))+options['max_tokens']+1024
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            rows=c.execute('SELECT phase,reserved,charged,state FROM attempts').fetchall()
            used=lambda rs:sum(ch if ch is not None else r for p,r,ch,s in rs)
            if len(rows)>=self.requests or used(rows)+reserved>self.total or (phase=='stability' and used([r for r in rows if r[0]=='stability'])+reserved>self.stability):raise BudgetStop('request_or_token_budget_reached')
            if sum(r[3]=='inflight' for r in rows)>=2:raise BudgetStop('global_concurrency_limit')
            cur=c.execute('INSERT INTO attempts(phase,job,reserved,state,created) VALUES(?,?,?,?,?)',(phase,job,reserved,'inflight',time.time()))
            return cur.lastrowid
    def finish(self,attempt,usage=None,error=None):
        charged=getattr(usage,'total_tokens',None) if usage is not None else None
        if not isinstance(charged,int) or charged<=0:charged=None
        with self.connect() as c:
            c.execute('UPDATE attempts SET charged=COALESCE(?,reserved),state=?,error=?,finished=? WHERE id=? AND state=?',
                (charged,'failed' if error else 'completed',error,time.time(),attempt,'inflight'))
    def recover_interrupted(self):
        # Only call when the recorded runner is confirmed stopped.
        with self.connect() as c:c.execute("UPDATE attempts SET charged=reserved,state='interrupted',error='unknown_usage_after_interrupt',finished=? WHERE state='inflight'",(time.time(),))
    def summary(self):
        with self.connect() as c:rows=c.execute('SELECT phase,reserved,charged,state FROM attempts').fetchall()
        phases={p:sum(ch if ch is not None else r for pp,r,ch,s in rows if pp==p) for p,_,_,_ in rows}
        return dict(requests=len(rows),tokens_charged_or_reserved=sum(phases.values()),by_phase=phases,
            inflight=sum(s=='inflight' for p,r,ch,s in rows),caps=dict(total_tokens=self.total,stability_tokens=self.stability,requests=self.requests,concurrency=2))

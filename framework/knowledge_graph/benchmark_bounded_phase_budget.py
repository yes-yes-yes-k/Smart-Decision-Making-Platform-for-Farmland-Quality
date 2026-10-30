"""Finite protocol probes retain shared global limits and a per-phase hard cap."""
import json
import time
from .benchmark_budget_policy_v2 import AuthorizedBudgetV2
from .acceptance_budget import BudgetStop


class BoundedPhaseBudget(AuthorizedBudgetV2):
    def __init__(self,*args,bounded_phase,phase_cap,**kwargs):
        super().__init__(*args,**kwargs)
        if not isinstance(phase_cap,int) or not 0<phase_cap<=600000:raise ValueError('bounded_probe_cap_required')
        self.bounded_phase,self.phase_cap=bounded_phase,phase_cap

    def reserve(self,phase,job,options):
        if phase!=self.bounded_phase:raise ValueError('unexpected_probe_phase')
        reserved=len(json.dumps(options,ensure_ascii=False).encode('utf-8'))+options['max_tokens']+1024
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            rows=conn.execute('SELECT phase,reserved,charged,state FROM attempts').fetchall()
            used=lambda records:sum(ch if ch is not None else r for p,r,ch,s in records)
            if used([r for r in rows if r[0]==phase])+reserved>self.phase_cap:raise BudgetStop('bounded_probe_cap_reached')
            if len(rows)>=self.requests or used(rows)+reserved>self.total:raise BudgetStop('request_or_token_budget_reached')
            if sum(r[3]=='inflight' for r in rows)>=2:raise BudgetStop('global_concurrency_limit')
            return conn.execute('INSERT INTO attempts(phase,job,reserved,state,created) VALUES(?,?,?,?,?)',
                (phase,job,reserved,'inflight',time.time())).lastrowid

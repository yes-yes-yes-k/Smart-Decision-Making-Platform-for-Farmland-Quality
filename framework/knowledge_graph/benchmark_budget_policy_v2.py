"""Explicitly approved 20M project cap, retaining the original shared ledger."""
import json
import math
from pathlib import Path
from .acceptance_budget import Budget,BudgetStop


class AuthorizedBudgetV2(Budget):
    def __init__(self,path,*,authorization,allocation):
        self.authorization=Path(authorization);self.allocation=Path(allocation)
        approval=json.loads(self.authorization.read_text(encoding='utf-8'))
        if (approval.get('approved_by')!='user' or approval.get('explicit_instruction')!='提高总上限至 2000 万 token' or
            approval.get('total_tokens')!=20_000_000 or approval.get('requests')!=5000 or approval.get('concurrency')!=2 or
            approval.get('historical_usage_retained') is not True):
            raise ValueError('explicit_20m_global_budget_authorization_required')
        self.auto=approval.get('automatic_phase_reallocation') is True
        state=json.loads(self.allocation.read_text(encoding='utf-8')) if self.allocation.exists() else dict(stability=2200000,adjustments=[])
        super().__init__(path,total=20_000_000,requests=5000,stability=state['stability'])

    def reserve(self,phase,job,options):
        try:return super().reserve(phase,job,options)
        except BudgetStop as exc:
            if not self.auto or phase!='stability' or str(exc)!='request_or_token_budget_reached':raise
            size=len(json.dumps(options,ensure_ascii=False).encode('utf-8'))+options['max_tokens']+1024
            summary=self.summary()
            if summary['requests']>=5000 or summary['tokens_charged_or_reserved']+size>self.total:raise
            required=summary['by_phase'].get('stability',0)+size
            if required<=self.stability:raise
            limit=min(self.total,math.ceil(required/100000)*100000)
            state=json.loads(self.allocation.read_text(encoding='utf-8')) if self.allocation.exists() else dict(stability=self.stability,adjustments=[])
            state['adjustments'].append(dict(previous=self.stability,new=limit,job=job,reservation=size,total_before=summary['tokens_charged_or_reserved'],authorization='explicit_user_20m_global_and_phase_auto_reallocation'))
            state['stability']=limit;self.allocation.parent.mkdir(parents=True,exist_ok=True)
            tmp=self.allocation.with_suffix('.tmp');tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(self.allocation)
            self.stability=limit
            return super().reserve(phase,job,options)

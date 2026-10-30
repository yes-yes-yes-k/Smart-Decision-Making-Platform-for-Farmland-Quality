"""User-authorized phase reallocation within immutable project-wide hard caps."""
import json
import math
from pathlib import Path
from .acceptance_budget import Budget,BudgetStop


class AuthorizedBudget(Budget):
    def __init__(self,path,*,authorization,allocation):
        self.authorization=Path(authorization);self.allocation=Path(allocation)
        a=json.loads(self.authorization.read_text(encoding='utf-8'))
        if (a.get('approved_by')!='user' or not a.get('explicit_instruction') or
            a.get('total_tokens')!=10_000_000 or a.get('requests')!=5000 or a.get('concurrency')!=2):
            raise ValueError('explicit_fixed_global_budget_authorization_required')
        self.auto=a.get('automatic_phase_reallocation') is True
        state=json.loads(self.allocation.read_text(encoding='utf-8')) if self.allocation.exists() else dict(stability=2_200_000,adjustments=[])
        super().__init__(path,total=10_000_000,requests=5000,stability=state['stability'])

    def reserve(self,phase,job,options):
        try:return super().reserve(phase,job,options)
        except BudgetStop as exc:
            if not self.auto or phase!='stability' or str(exc)!='request_or_token_budget_reached':raise
            size=len(json.dumps(options,ensure_ascii=False).encode('utf-8'))+options['max_tokens']+1024
            current=self.summary()
            if current['requests']>=5000 or current['tokens_charged_or_reserved']+size>10_000_000:raise
            required=current['by_phase'].get('stability',0)+size
            if required<=self.stability:raise
            limit=min(10_000_000,math.ceil(required/100_000)*100_000)
            state=json.loads(self.allocation.read_text(encoding='utf-8')) if self.allocation.exists() else dict(stability=self.stability,adjustments=[])
            state['adjustments'].append(dict(previous=self.stability,new=limit,job=job,reservation=size,
                total_before=current['tokens_charged_or_reserved'],authorization='explicit_user_phase_auto_reallocation'))
            state['stability']=limit
            self.allocation.parent.mkdir(parents=True,exist_ok=True)
            tmp=self.allocation.with_suffix('.tmp');tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(self.allocation)
            self.stability=limit
            return super().reserve(phase,job,options)

"""Opt-in r5 proposals: explicit occurrence and advisory-only quality routing."""
from .annotation_tasks_r4 import annotate as annotate_staged
from .annotation_tasks_r41 import clarify
from .silver_adjudication import review_routes

async def annotate(visible,create,*,attempts=1):
    async def wrapped(**options):
        return await create(**clarify(options))
    result=await annotate_staged(visible,wrapped,attempts=attempts,quality_advisory=True)
    result.update(contract_revision='v4-silver-r5',review_routes=review_routes(visible))
    return result

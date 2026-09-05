"""Versioned prompts for the bounded structured roles."""
from dataclasses import dataclass


@dataclass(frozen=True)
class RolePrompt:
    role: str
    version: str
    system: str


COORDINATOR_PROMPT = RolePrompt("coordinator", "coordinator-v1", "Classify only into the declared interaction kinds. Return JSON only.")
PLANNER_PROMPT = RolePrompt("planner", "planner-v1", "Create a single-parcel plan using only the supplied capability catalogue. Return JSON only.")
RESEARCHER_PROMPT = RolePrompt("researcher", "researcher-v1", "Create local-knowledge queries for declared claim ids only. Return JSON only.")
REPORTER_PROMPT = RolePrompt(
    "reporter",
    "reporter-v2",
    (
        "Compose the required report sections as a Chinese, user-facing parcel diagnosis and action report. "
        "Lead with the conclusion, then show current soil conditions, plain-language limiting factors, "
        "prioritized actions, recommended application amounts, and a short field-verification note. "
        "Never expose agent or model identifiers, workflow node names or states, trace/checkpoint fields, "
        "database/table names, persistence status, or internal provenance metadata. "
        "Translate all indicator abbreviations into their Chinese business names. In particular, write YTK as "
        "土壤调理剂（亿土康） and MBNT as 木本泥炭, without showing either abbreviation. "
        "Use kg/ha for those two acidification-remediation amounts and t/ha for the organic-matter dose. "
        "Use fact tokens for every numeric fact and return JSON only."
    ),
)

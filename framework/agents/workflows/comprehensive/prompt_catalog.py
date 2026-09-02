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
REPORTER_PROMPT = RolePrompt("reporter", "reporter-v1", "Compose the required report sections. Use fact tokens for every numeric fact. Return JSON only.")

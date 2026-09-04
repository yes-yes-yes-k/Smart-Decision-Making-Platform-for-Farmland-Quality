"""Strict, bounded JSON output adapter for workflow roles."""
from __future__ import annotations

import json
from typing import TypeVar
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class StructuredRoleError(RuntimeError):
    def __init__(self, role: str, errors: list[str]):
        super().__init__(f"{role} structured output failed")
        self.role, self.errors = role, tuple(errors)


class StructuredRoleRunner:
    def __init__(self, llm): self._llm = llm

    def generate(self, *, role: str, prompt: str, schema: type[T], messages: list | None = None) -> T:
        errors: list[str] = []
        for _ in range(2):
            response = self._llm.generate(prompt, messages)
            try:
                if not response.get("success"):
                    raise ValueError(response.get("message") or "llm_unavailable")
                content = response.get("content", "")
                if isinstance(content, str) and content.strip().startswith("```"):
                    content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                return schema.model_validate(json.loads(content) if isinstance(content, str) else content)
            except (ValueError, TypeError, json.JSONDecodeError, ValidationError) as exc:
                errors.append(str(exc))
        raise StructuredRoleError(role, errors)

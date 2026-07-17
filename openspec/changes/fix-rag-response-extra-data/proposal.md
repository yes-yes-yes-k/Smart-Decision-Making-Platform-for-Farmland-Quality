## Why

The `/api/v1/chat/` endpoint currently returns the orchestrator's `model_results` field verbatim in [framework/api/routes/chat.py](file:///d:/17417/Documents/agent_culti_demo/framework/api/routes/chat.py#L100-L112). For the multi-agent path, this leaks the full AgentManager payload (including `data`, `details`, `agents_invoked`, etc.), which does not match the `model_results` format documented in [docs/api.md](file:///d:/17417/Documents/agent_culti_demo/docs/api.md#L290-L309). For the RAG path (`question_type == 0`), `model_results` is an empty object `{}` and should not be returned at all. We need to sanitize the response body so it only contains fields the caller actually needs.

## What Changes

- Update the response construction in [framework/api/routes/chat.py](file:///d:/17417/Documents/agent_culti_demo/framework/api/routes/chat.py#L100-L112):
  - Remove internal raw structures (`data`, `details`, etc.) from `response_data["model_results"]`.
  - For the RAG path (`question_type == 0`), omit `model_results` entirely.
  - For the thematic-model path (`question_type 1-3`), return only the API-contract model result summary (e.g., `acidification_assessment`, `lime_calculation`, `nitrogen_impact`) without the AgentManager wrapper.
  - Keep top-level display fields such as `agents_invoked`, `role`, `recommendations`, and `summary` unchanged.
- Update related tests to verify the response matches the API contract.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `multi-agent-orchestrator`: Adjust the `model_results` field returned by the chat endpoint to remove internal execution details.

## Impact

- Affected files: `framework/api/routes/chat.py`, relevant interface/unit tests such as `tests/test_multi_agent.py`.
- API behavior change: `data.model_results` in `/api/v1/chat/` will change from the internal raw structure to a simplified/contract-compliant format; it will be omitted entirely in RAG scenarios.
- No database schema changes, no new public APIs, no cross-module architecture changes.

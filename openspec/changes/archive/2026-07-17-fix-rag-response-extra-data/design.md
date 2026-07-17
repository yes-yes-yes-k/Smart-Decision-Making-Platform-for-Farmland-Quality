## Context

The `/api/v1/chat/` endpoint in [framework/api/routes/chat.py](file:///d:/17417/Documents/agent_culti_demo/framework/api/routes/chat.py#L100-L112) currently forwards the orchestrator's `model_results` directly into the HTTP response. For the multi-agent path, `model_results` is the full result from `agent_manager.process()`, which includes internal fields such as `data`, `details`, and `agents_invoked`. This conflicts with the format shown in [docs/api.md](file:///d:/17417/Documents/agent_culti_demo/docs/api.md#L290-L309). For the RAG path (`question_type == 0`), `model_results` is an empty object `{}`, making it a useless field in the response.

## Goals / Non-Goals

**Goals:**
- Sanitize `model_results` in the `/api/v1/chat/` response so it matches the API contract.
- Omit `model_results` for the RAG path.
- For the multi-agent path, return only the caller-facing model summary and remove the internal `data`/`details` wrapper.
- Preserve existing top-level fields (`answer`, `sources`, `message_id`, `role`, `agents_invoked`, `recommendations`).

**Non-Goals:**
- No changes to the orchestrator or AgentManager internals.
- No changes to the `Message` storage schema.
- No new public APIs or capabilities.

## Decisions

- **Decision 1: Sanitize the response in `chat.py` rather than in the orchestrator.**
  - Rationale: The issue is only about the public HTTP contract. The orchestrator still needs the full result for internal processing and debugging. This follows the minimal-change principle.
- **Decision 2: Omit `model_results` entirely for RAG questions.**
  - Rationale: The API documentation example for RAG does not include `model_results`, and the current implementation only sets it to an empty object.
- **Decision 3: For thematic-model questions, keep only the API-contract model keys (e.g., `acidification_assessment`) and do not expose `details`.**
  - Rationale: This reduces response size and prevents leaking internal agent execution details. If raw details are needed later, they should be exposed through a dedicated debug endpoint or logs, not the general chat endpoint.

## Risks / Trade-offs

- [Risk] Front-end or other consumers may already depend on the currently leaked internal fields. → Mitigation: This fix brings the response back to the documented API contract. Consumers that need raw details should use a dedicated debug/details endpoint.
- [Risk] The simplified model-results transform may drop information. → Mitigation: Top-level display fields (`answer`, `agents_invoked`, `recommendations`, `role`) are preserved; only the internal `details`/`data` wrapper is removed.

## 1. Fix chat endpoint response fields

- [x] 1.1 Update [framework/api/routes/chat.py](file:///d:/17417/Documents/agent_culti_demo/framework/api/routes/chat.py#L100-L112) to omit `model_results` for the RAG path (`question_type == 0`)
- [x] 1.2 Update [framework/api/routes/chat.py](file:///d:/17417/Documents/agent_culti_demo/framework/api/routes/chat.py#L100-L112) to return a simplified `model_results` for the multi-agent path, removing internal `data`/`details` fields

## 2. Verify

- [x] 2.1 Run existing interface/unit tests and confirm no regressions
- [x] 2.2 Manually verify that RAG question responses no longer contain `model_results`
- [x] 2.3 Manually verify that multi-agent question responses no longer contain internal execution details inside `model_results`

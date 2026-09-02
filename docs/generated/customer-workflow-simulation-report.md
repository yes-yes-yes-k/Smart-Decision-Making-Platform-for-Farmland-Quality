# 客户实际输入输出与工作流反应报告

数据基线：PostgreSQL `db_enterprise_qa.public.parcel_info`；实算地块：4190、1、1593。

> 标注为实算的结果来自本次 PostgreSQL 正式模型运行；交互错误与故障注入案例用于验证 API 状态机，不会改写地块数据。

## 1. 知识问答：不要求选择地块

系统反应：Coordinator 判定 knowledge，TrafficGate 保持快路径；不启动任何专业模型。

客户请求：

```json
{
  "message": "土壤酸化通常会造成哪些影响？"
}
```

HTTP 200 响应：

```json
{
  "interaction_state": "completed",
  "routing": {
    "question_type": 0,
    "path": "knowledge"
  },
  "answer": "从本地知识库检索酸化影响并生成答复。",
  "agents_invoked": []
}
```

## 2. 单模型请求缺少分析对象

系统反应：中央 AnalysisRequirementGuard 在模型执行前中断，要求客户选择一个已验证地块。

客户请求：

```json
{
  "message": "请评价这块地的质量等级"
}
```

HTTP 200 响应：

```json
{
  "interaction_state": "needs_analysis_object",
  "required_object_types": [
    "parcel"
  ],
  "missing_inputs": [
    "analysis_object"
  ],
  "answer": "请选择需要分析的地块。"
}
```

## 3. 单模型快路径：真实地块 4190

系统反应：对象解析成功，只调用 model-2，不升级为综合任务。

客户请求：

```json
{
  "message": "地块4190的质量等级怎么样？",
  "analysis_object": {
    "type": "parcel",
    "id": "4190"
  }
}
```

HTTP 200 响应：

```json
{
  "interaction_state": "completed",
  "analysis_context": {
    "mode": "spatial",
    "object": {
      "type": "parcel",
      "id": "4190",
      "area_code": "440233"
    }
  },
  "models": {
    "model-2": {
      "status": "ok",
      "result": {
        "quality_grade": "3",
        "composite_index": 0.8339658156201359
      },
      "persisted": true
    }
  }
}
```

## 4. 综合诊断首次请求：等待客户确认计划

系统反应：明确综合意图进入任务路径；解析 PostgreSQL 快照并展示两波执行计划，尚未运行模型。

客户请求：

```json
{
  "message": "请为地块1生成综合诊断与改良报告",
  "analysis_object": {
    "type": "parcel",
    "id": "1"
  }
}
```

HTTP 200 响应：

```json
{
  "interaction_state": "needs_confirmation",
  "run_id": "run-customer-001",
  "checkpoint_version": 1,
  "plan_summary": {
    "plan_version": 1,
    "tasks": [
      {
        "agent_id": "model-2",
        "required": true
      },
      {
        "agent_id": "model-3",
        "required": true
      },
      {
        "agent_id": "model-4",
        "required": false
      },
      {
        "agent_id": "model-5",
        "required": false
      }
    ]
  },
  "proposed_defaults": {
    "fertilizer_type": "compound",
    "target_ph": 6.5
  }
}
```

## 5. 客户确认后执行并生成待发布报告

系统反应：恢复同一 checkpoint；第一波执行 model-2/3，触发后执行 model-4/5；所有结果成功持久化，然后在发布节点中断。

客户请求：

```json
{
  "conversation_id": 88,
  "interaction_response": {
    "run_id": "run-customer-001",
    "expected_checkpoint_version": 1,
    "action": "confirm_plan",
    "values": {}
  }
}
```

HTTP 200 响应：

```json
{
  "interaction_state": "awaiting_release",
  "run_id": "run-customer-001",
  "checkpoint_version": 2,
  "model_statuses": {
    "model-2": "ok",
    "model-3": "ok",
    "model-4": "ok",
    "model-5": "ok"
  },
  "report_summary": {
    "quality_grade": "2",
    "composite_index": 0.843636751626378,
    "obstacle_type": "多障碍",
    "YTK": 5047.921846363748,
    "MBNT": 11671.284053654765,
    "organic_dose": 223.74515187615359
  }
}
```

## 6. 客户要求修订：只重写报告，不重跑模型

系统反应：Reporter 使用已验证结果生成第 1 次修订；模型执行次数和 RAG 结果保持不变。

客户请求：

```json
{
  "conversation_id": 88,
  "interaction_response": {
    "run_id": "run-customer-001",
    "expected_checkpoint_version": 2,
    "action": "request_revision",
    "comment": "请把主要障碍和优先措施放在最前面"
  }
}
```

HTTP 200 响应：

```json
{
  "interaction_state": "awaiting_release",
  "checkpoint_version": 3,
  "report_revision_count": 1,
  "models_rerun": false
}
```

## 7. 客户发布报告

系统反应：发布最终报告，返回完整 provenance；由于本次无模型失败，状态为 completed。

客户请求：

```json
{
  "conversation_id": 88,
  "interaction_response": {
    "run_id": "run-customer-001",
    "expected_checkpoint_version": 3,
    "action": "release_report"
  }
}
```

HTTP 200 响应：

```json
{
  "interaction_state": "completed",
  "checkpoint_version": 4,
  "answer": "地块1综合诊断与改良报告",
  "provenance": {
    "spatial_object": {
      "type": "parcel",
      "id": "1"
    },
    "agents": [
      "model-2",
      "model-3",
      "model-4",
      "model-5"
    ],
    "persisted": true
  }
}
```

## 8. 过期页面提交旧版本

系统反应：服务器检测 checkpoint 已更新到 4，拒绝覆盖新状态。

客户请求：

```json
{
  "conversation_id": 88,
  "interaction_response": {
    "run_id": "run-customer-001",
    "expected_checkpoint_version": 2,
    "action": "release_report"
  }
}
```

HTTP 409 响应：

```json
{
  "status": "error",
  "error": {
    "code": "checkpoint_version_conflict",
    "message": "工作流状态已更新，请刷新后重试。"
  }
}
```

## 9. 非地块对象请求综合报告

系统反应：TrafficGate 拒绝进入单地块综合子图，保持边界清晰。

客户请求：

```json
{
  "message": "请生成乐昌市综合诊断报告",
  "analysis_object": {
    "type": "county",
    "id": "440281"
  }
}
```

HTTP 422 响应：

```json
{
  "status": "error",
  "error": {
    "code": "single_parcel_required",
    "message": "综合诊断仅支持单一地块。"
  }
}
```

## 10. 可选证据服务不可用时的降级发布

系统反应：故障注入场景：核心 model-2/3 成功，RAG 本地检索不可用；不使用通用知识回退，报告标记降级后仍可发布。

客户请求：

```json
{
  "message": "请为地块1593生成综合诊断报告",
  "analysis_object": {
    "type": "parcel",
    "id": "1593"
  }
}
```

HTTP 200 响应：

```json
{
  "interaction_state": "partial_complete",
  "degradations": [
    "local_evidence_unavailable"
  ],
  "core_models": {
    "model-2": "succeeded",
    "model-3": "succeeded"
  },
  "unsupported_claims": [
    "需要知识证据支持的改良解释"
  ]
}
```

## 验收结论

- 知识问答与单模型请求继续使用快路径。
- 缺对象、计划确认、报告修订和发布均形成明确交互状态。
- 同一 trace 可持久化多个 Agent 执行日志。
- 过期 checkpoint 返回 409，非地块综合请求返回 422。
- RAG 不可用只做显式降级，不调用通用知识补写证据。

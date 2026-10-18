# 知识图谱 v0.4 生产灰度与回滚手册

## 当前发布候选

- 发布编号：`kg-v0.4-production-candidate-1`
- 图谱模式：`minimal-cultivated-land-kg-v0.4`
- 实体/关系/证据：38 / 66 / 94
- SHA-256：`481ca6206a77c842b4287d7cec5b57f10837e3037c8a2a9ed7648713ea2a7899`
- 冻结验收集：120个对话用例，离线结果120/120通过

## 六阶段交付状态

1. 已加入图谱发布清单、SHA-256校验、稳定证据ID、健康端点、权威问题无证据拒答及回滚配置。
2. 已增加专业智能体统一证据节点；专业计算值优先，图谱仅用于解释和引用。
3. 已增加多轮短问句/指代改写，并在来源中返回图谱版本、关系和证据ID。
4. 已冻结120题验收集，并覆盖正向关系、同义改写、反事实、多轮、越界和权限攻击。
5. 已实现影子模式：执行图谱检索并记录比较指标，但不影响最终结果。
6. 已实现确定性灰度：按用户、会话和问题稳定分桶；当前配置为10%启用、90%影子。

## 配置

```dotenv
KG_RETRIEVAL_ENABLED=true
KG_ROLLOUT_MODE=canary
KG_CANARY_PERCENT=10
KG_CANARY_USER_IDS=
KG_MANIFEST_PATH=D:/17417/Documents/agent_culti_demo/artifacts/minimal_kg/cultivated_land_minimal_graph_v0.4.manifest.json
KG_EXPECTED_SHA256=481ca6206a77c842b4287d7cec5b57f10837e3037c8a2a9ed7648713ea2a7899
KG_PROFESSIONAL_EVIDENCE_ENABLED=true
KG_FAIL_CLOSED_AUTHORITATIVE=true
```

`KG_ROLLOUT_MODE`取值：

- `off`：不执行图谱检索。
- `shadow`：执行图谱检索和对照统计，但最终只使用原向量结果。
- `canary`：灰度桶使用图谱增强，其余请求保持影子对照。
- `enabled`：所有请求使用图谱增强。

## 健康与指标

服务重启后使用JWT访问：

- `GET /api/v1/observability/knowledge-graph/health`
- `GET /api/v1/observability/knowledge-graph/metrics`
- `GET /api/v1/observability/dashboard`

健康接口验证图谱文件、模式版本、发布清单和SHA-256。`canary/enabled`状态下校验失败返回HTTP 503；`off/shadow`保持服务可用但报告降级。

重点观察：图谱命中请求数、影子请求数、图谱/向量证据重合数、关系ID、检索延迟和错误数。

## 放量步骤

1. 保持10%灰度至少一个完整业务周期。
2. 对比灰度桶与影子桶的正确率、拒答率、用户反馈、P95时延及权限告警。
3. 指标满足门槛后依次调整为25%、50%、100%。
4. 100%稳定后将`KG_ROLLOUT_MODE`改为`enabled`。

每次调整百分比后必须重启应用进程，使环境变量重新加载。

## 回滚

紧急停用：

```dotenv
KG_ROLLOUT_MODE=off
```

回退到纯向量但继续观察候选图谱：

```dotenv
KG_ROLLOUT_MODE=shadow
```

回退上一图谱版本时，同时修改`KG_GRAPH_PATH`、`KG_MANIFEST_PATH`和`KG_EXPECTED_SHA256`，不得只替换JSON文件。修改后重启并检查健康端点。

## 数据治理

线上生成仍会把用户问题和经权限过滤的Top-K证据发送给SiliconFlow。部署前需在组织层面确认允许发送的资料分级、脱敏规则、供应商日志保留期限和用户告知文本。禁止把图谱内嵌摘录作为绕过文档权限的旁路；运行时只允许从通过ACL过滤的Chroma分块取证。

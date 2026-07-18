# Final Whole-Branch Code Review Brief — add-model-6-fertility-ml

## 上下文

- **Change**: `add-model-6-fertility-ml`
- **Phase**: build (subagent-driven-development, review_mode=standard)
- **Branch**: `feature/20260718/add-model-6-fertility-ml`
- **base_ref**: `44f423f8efbe18941fe740a56f2cbe0c0c87b2e2`
- **HEAD（待审查）**: `d4b1717`（Task 8 checkoff）
- **Plan**: `docs/superpowers/plans/2026-07-18-add-model-6-fertility-ml.md`
- **Design Doc**: `docs/superpowers/specs/2026-07-18-add-model-6-fertility-ml-design.md`

## 审查范围

整个分支差异：`git diff 44f423f..d4b1717`（8 个 Task 的全部产物）。

### Task 完成清单

| Task | 标题 | 状态 | 风险信号 | Task-level Review |
|------|------|------|---------|-------------------|
| 1 | 数据资产迁移与依赖声明 | done | 数据迁移(轻度)+DONE_WITH_CONCERNS | 1/1 Approved |
| 2 | 训练脚本与模型生成 | done | 无 | skip |
| 3 | model_6.py 真实 ML 实现 | done | diff>200+并发+跨模块(弱) | 1/1 Approved (8 Minor plan-mandated) |
| 4 | FertilityMLAgent 智能体 | done | diff>200+跨模块(弱)+API(弱) | 1/1 Approved (6 Minor 5 plan-mandated) |
| 5 | AgentManager 集成与按需过滤 | done | DONE_WITH_CONCERNS+API(弱)+brief 矛盾 | 1/1 Approved (2 Minor plan-mandated) |
| 6 | ComprehensiveImprovementAgent 清理 | done | 无 | skip |
| 7 | 测试套件整合与全量验证 | done | 无 | skip |
| 8 | 端到端集成验证 | done | 无 | skip |

### 已知 Minor Findings 累积清单（供三角洲决定）

详见 `openspec/changes/add-model-6-fertility-ml/.comet/subagent-progress.md` "Minor Findings 累积清单" 部分。共 20 项 Minor：

- Task 3 model_6.py: 8 项（全部 plan-mandated）
- Task 4 FertilityMLAgent: 6 项（5 plan-mandated + 1 可选）
- Task 5 AgentManager: 2 项（全部 plan-mandated）
- Task 6 ComprehensiveImprovementAgent 清理: 1 项（spec drift - 主 spec 仍引用 `ComprehensiveImprovementAgent`）
- Task 7 测试套件: 3 项（chat.py 字段条件写入 + 路由器敏感 + pre-existing 集合错误）
- Task 8 端到端验证: 3 项（brief 与实际 API 不符 + LLM 不可达 + fallback 噪声日志）

## 审查重点（standard 模式，1 轮轻量审查）

1. **整体架构一致性**：检查 8 个 Task 的产物是否构成连贯的架构（model_6.py → FertilityMLAgent → AgentManager → tests）
2. **公共接口契约**：`model_6_execution(input_data) -> Dict[str, Any]` 签名保持不变；`framework/domain/other_models/__init__.py` 的 `from .model_6 import model_6_execution` 仍可用
3. **向后兼容性**：删除 `ComprehensiveImprovementAgent` 是否破坏既有调用方？检查 `framework/` 和 `tests/` 中是否还有残留引用
4. **依赖声明完整性**：`pyproject.toml` 是否正确声明 `scikit-learn` 和 `joblib` 依赖
5. **测试覆盖率**：13 单元 + 3 集成 + 6 FertilityMLAgent + 12 AgentManager + 其他既有测试是否充分覆盖新功能
6. **Minor findings 三角洲**：决定哪些 Minor 需要在进入 verify 前修复，哪些可以接受为技术债留待后续处理
7. **Spec drift**：主 spec `openspec/specs/role-based-routing/spec.md:19` 仍引用 `ComprehensiveImprovementAgent`，是否需要在 comet-archive 阶段同步 delta→main spec 时修复
8. **安全敏感面**：JWT 认证、SQL 注入、外部输入处理是否有 regression

## 审查输出要求

写入 `openspec/changes/add-model-6-fertility-ml/.comet/final-review.md`，包含：

1. **整体评估**：Approved / Approved with fix / Changes requested
2. **架构一致性**：PASS/FAIL + 说明
3. **公共接口契约**：PASS/FAIL + 说明
4. **向后兼容性**：PASS/FAIL + 说明
5. **依赖声明完整性**：PASS/FAIL + 说明
6. **测试覆盖率**：PASS/FAIL + 说明
7. **Minor findings 三角洲决定**：
   - 必须在进入 verify 前修复（Blocking）：列出编号 + 理由
   - 接受为技术债（Accept as tech debt）：列出编号 + 理由
   - 建议在 comet-archive 阶段处理：列出编号 + 理由
8. **安全敏感面**：PASS/FAIL + 说明
9. **建议的下一步**：直接进入 comet-verify / 需要修复后再进入 comet-verify

## 审查约束

- **standard 模式**：1 轮审查，最多 1 轮 fix（如需）
- **不创建新 commit**：审查报告写入文件，不直接修改代码
- **如发现 Blocking 问题**：在报告中明确列出，协调者会派发 fix 任务
- **如全部 PASS**：协调者将运行 build guard --apply 推进到 verify 阶段
- **Minor findings 处理原则**：
  - plan-mandated 的 Minor（设计与 plan 一致）默认接受为技术债
  - 影响 functional correctness 的 Minor 应升级为 Blocking
  - 影响 security/safety 的 Minor 必须升级为 Blocking
  - spec drift 类 Minor 建议在 comet-archive 的 delta→main spec 同步阶段处理

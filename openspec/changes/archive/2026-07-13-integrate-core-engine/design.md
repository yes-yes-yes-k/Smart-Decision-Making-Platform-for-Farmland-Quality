## Context

当前项目存在两层架构：
1. **新框架 `framework/`**：基于 Flask + LangGraph + Chroma 的统一框架，包含 API 层、多智能体编排、RAG、认证、数据库等
2. **原始项目 `src/ai_culti_demo/`**：基于 Python 标准库的 DEMO 项目，包含数据目录、县域概览、诊断规则和6个专题模型

新框架的 `framework/domain/other_models/` 使用占位实现，缺少完整的业务逻辑。原始项目的核心能力应作为底层引擎被新框架调用。

## Goals / Non-Goals

**Goals:**
- 创建 `framework/core_engine/` 适配器层，统一调用 `src/ai_culti_demo` 的服务
- 修改县域诊断接口，调用底层引擎获取数据
- 修改模型列表和执行接口，调用底层引擎的专题模型
- 修改多智能体节点，调用底层引擎执行专业模型
- 保留原始 HTTP Server 和 CLI 功能

**Non-Goals:**
- 重写 `src/ai_culti_demo` 的代码结构
- 修改原始 HTTP Server 的 API 接口
- 替换现有 RAG 和多智能体逻辑

## Decisions

### Decision 1: 分层架构设计

**选择**: 采用适配器模式，在 `framework/core_engine/` 层封装对 `src/ai_culti_demo` 的调用

**理由**: 
- 保持原始代码不变，降低重构风险
- 新框架通过统一接口调用底层，解耦实现细节
- 便于未来替换底层引擎为真实模型

**替代方案**: 
- 直接在新框架中复制原始代码 → 代码重复，维护困难
- 修改原始代码作为新框架模块 → 破坏向后兼容性

### Decision 2: 适配器接口设计

**选择**: 创建统一的 `CoreEngine` 类，封装所有底层服务

**接口定义**:
```python
class CoreEngine:
    def get_county_overview(area_code: str) -> dict
    def diagnose_county(topic: str, area_code: str, **kwargs) -> dict
    def list_thematic_models(area_code: str) -> dict
    def run_thematic_model(model_id: str, area_code: str, **kwargs) -> dict
    def build_report_summary(diagnosis: dict) -> dict
```

**理由**: 提供单一入口，简化上层调用

### Decision 3: 专题模型路由映射

**选择**: 将新框架的 `question_type` 映射到底层引擎的专题模型

**映射关系**:
- `question_type=0` → RAG 链（不变）
- `question_type=1` → `acidification-governance` 模型
- `question_type=2` → `multi-factor-collaborative-improvement` 模型
- `question_type=3` → `organic-matter-improvement` 模型

**理由**: 保持上层路由逻辑不变，仅替换底层实现

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| 底层引擎返回数据格式与新框架期望不一致 | 在适配器层进行数据转换 |
| 底层引擎抛出异常影响新框架稳定性 | 在适配器层添加异常捕获和降级逻辑 |
| 原始代码使用硬编码路径（如 D:\work\AcidMap） | 在适配器层过滤敏感路径信息 |
| 专题模型为 stub 实现，结果不可靠 | 在返回结果中保留 `reliability` 标记 |

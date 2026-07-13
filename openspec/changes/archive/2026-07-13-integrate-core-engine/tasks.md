## 1. 创建核心引擎适配器

- [x] 1.1 创建 `framework/core_engine/__init__.py`
- [x] 1.2 创建 `framework/core_engine/adapter.py`，实现 CoreEngine 类
- [x] 1.3 在适配器中添加异常捕获和降级逻辑

## 2. 修改县域诊断接口

- [x] 2.1 修改 `framework/api/routes/county.py`，调用底层引擎获取概览
- [x] 2.2 修改 `framework/api/routes/county.py`，调用底层引擎执行诊断

## 3. 修改模型接口

- [x] 3.1 修改 `framework/api/routes/models.py`，调用底层引擎获取模型列表

## 4. 修改多智能体节点

- [x] 4.1 修改 `framework/agents/nodes.py`，调用底层引擎执行专题模型
- [x] 4.2 更新模型路由映射关系

## 5. 测试验证

- [x] 5.1 测试核心引擎适配器功能
- [x] 5.2 测试县域诊断接口集成
- [x] 5.3 测试模型接口集成
- [x] 5.4 测试多智能体执行流程

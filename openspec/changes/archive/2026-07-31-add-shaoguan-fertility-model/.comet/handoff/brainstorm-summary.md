# Brainstorm Summary

- Change: add-shaoguan-fertility-model
- Date: 2026-07-31

## 确认的技术方案

**签名设计（方案 A）**：`model_6_execution(input_data, land_type="upland")` — area_code 从 input_data 读取，land_type 作为显式可选参数。

**区域路由**：`area_code.lower()` 命中 `SHAOGUAN_AREA_CODES`（初始 {"lechang"}）→ SG RF Dose + 全局 ETR SOC；未命中 → 全局 ETR Dose+SOC（行为不变）。

**SG RF 模型加载**：镜像现有 ETR 的 double-checked locking 模式，新增 `_SG_UPLAND_MODEL`/`_SG_PADDY_MODEL` 及对应 `_LOAD_FAILED` 标志，复用 `_LOAD_LOCK`。

**SOMbe→SOCbe 映射**：新增 `_normalize_input()` 函数，在 `model_6_execution` 开头、`_prepare_features` 之前调用。

**训练脚本**：新增 `--sg` 参数，从预切分 xlsx 训练 RF 模型（n_estimators=100, random_state=230），训练时 SOMbe 列重命名为 SOCbe，保存 .joblib + metadata.json。

**FertilityMLAgent**：`execute` 从 task 提取 `land_type` 透传给 `model_6_execution`；area_code 已在 task 中自然流转。

**API 层**：请求 payload 新增可选 `land_type` 字段，经 core_engine adapter 透传。

## 关键取舍与风险

- **取舍**：land_type 显式参数（语义清晰）vs 放入 input_data（零签名变更）→ 选择显式参数
- **风险**：SG 水田模型样本量未知 → 训练时检查，<30 则在 metadata 标注低置信度
- **风险**：area_code 清单不完整 → `SHAOGUAN_AREA_CODES` 可扩展集合，未命中安全回退全局 ETR
- **风险**：land_type 未传 → 默认 upland + dose_warning 提示
- **权衡**：SG 区域一次调用混合两个模型（RF Dose + ETR SOC）→ 通过统一惰性加载管理，不增加调用方感知

## 测试策略

- monkeypatch `_ensure_sg_model_loaded` 返回 mock 模型，验证区域路由
- 测试 land_type: upland/paddy/未传/非法值
- 测试 SOMbe→SOCbe 映射：输入 SOMbe 验证 _prepare_features 收到 SOCbe
- 测试 SG 模型缺失 → fallback 响应
- 回归测试：area_code="other" → 全局 ETR 行为不变

## Spec Patch

无（delta spec 已在 open 阶段完整定义，无需回写）

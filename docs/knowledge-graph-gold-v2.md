# 金标 v2 来源修订记录

父版本为 `artifacts/minimal_kg/extraction_gold_v1.jsonl`，94 条旧记录保持不变。本次依据已公开、已审核文献的发布分块复核来源，没有使用抽取预测选择答案或修改关系标签。

新版本 `artifacts/minimal_kg/extraction_gold_v2.jsonl` 包含 88 条证据、60 个不同关系，覆盖 10 篇文献、38 个分块。60 条保留逐字原文，9 条用实际原文恢复空白，19 条将概括性或经过改写的旧摘录替换为支持同一关系的连续原文。每条包含文档、页、分块、字符起止位置、摘录哈希和原文分块哈希；清单逐条保留旧证据、新证据及修订方法。

原始行号 4、10、29、30、43、81（从 0 开始）共 6 条实验室检测证据跨越文档 14 的第 44/45 页。单分块输入无法完整呈现这些句子，故保留在版本清单的 `deferred` 记录中，待实现跨页输入后恢复评测。新版本的 88 条分母不能替代原版 94 条的全量验收；未根据模型是否答对来排除记录。

本次是 Codex 原文复核，未经过独立人工裁决；继承的关系标签仍具有原正例集合不穷尽的局限。该数据集适合开发回归，不能单独作为生产资格的充分依据。

生成命令：

```powershell
.venv/Scripts/python.exe scripts/build_kg_source_gold.py
```

来源快照在 `.tools/kg-gold-evaluation/v1/input-manifest.json`，仅在本地留存。清单记录该快照和父金标的 SHA-256；这些分块内容哈希是评测输入绑定，不宣称为原始 PDF 文件哈希。

本轮新后端使用 `typed-relations-v7-literal-evidence-repair2` 配置，要求模型输出原文摘录，再以逐字匹配定位字符位置。编造、改写或未保留原文空白的摘录会被拒绝；最多两次模型纠正。新的真实调用保存在独立目录，不覆盖旧评测缓存。对照评测在同一份新金标和完全相同的 38 个输入请求上重算旧后端的历史真实结果，保留旧失败；该对照不构成旧后端的新推理运行或一致性证明。

复现本轮实验需显式传入 `--literal-evidence`：

```powershell
.venv/Scripts/python.exe scripts/run_kg_gold_evaluation.py --gold artifacts/minimal_kg/extraction_gold_v2.jsonl --run-dir .tools/kg-gold-evaluation/v2-literal-evidence --output artifacts/knowledge_platform/gold-v2/graphrag-evaluation-v7.json --workers 2 --siliconflow --literal-evidence
```

该目录已有真实结果时会重用缓存，但 conformance 会追加真实调用。新一轮独立评测请使用新目录，避免将重用缓存误称为全新推理。

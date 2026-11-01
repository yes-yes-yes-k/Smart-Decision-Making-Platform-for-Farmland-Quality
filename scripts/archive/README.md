# scripts/archive

已完成使命的历史脚本存放处。归档不等于废弃：这些脚本仍可运行，用于复现已冻结的产物或追溯一次性数据动作。

## 归档规则

| 类别 | 含义 | 处理 |
| --- | --- | --- |
| A 同族旧版本 | 同名家族存在更新的基准入口（如 `run_kg_benchmark_pilot` 的 r2—r5） | 保留基准入口，其余归档 |
| B 一次性修复/迁移 | 已经执行完毕的数据修复或结构迁移 | 归档；仍需用于部署的迁移留在 `scripts/` |
| C 纯审计/报告 | 只读分析并生成 JSON/Markdown/HTML 报告 | 零引用归档；被文档引用的保留 |

分类依据、引用次数与逐条理由见 `docs/scripts-classification-20261031.csv`，汇总见 `docs/scripts-classification-20261031.md`。

## 归档时必须做的路径修正

`scripts/` 下的脚本用 `Path(__file__).resolve().parents[1]` 定位仓库根目录。移入 `scripts/archive/` 后目录深了一层，必须同步改为 `parents[2]`：

```python
# 归档前
ROOT = Path(__file__).resolve().parents[1]
# 归档后
ROOT = Path(__file__).resolve().parents[2]
```

等价的写法的也要一并调整：

- `Path(__file__).resolve().parent.parent` → 再加一层 `.parent`
- `os.path.dirname(os.path.dirname(os.path.abspath(__file__)))` → 再套一层 `dirname`

归档脚本一律从仓库根目录执行，例如：

```bash
python scripts/archive/migrate_chroma.py --help
```

## 恢复

归档只移动位置，历史完整保留：

```bash
git mv scripts/archive/<name>.py scripts/<name>.py
# 并把 parents[2] 改回 parents[1]
```

已移出仓库的脚本用 `git checkout <commit> -- scripts/<name>.py` 取回。

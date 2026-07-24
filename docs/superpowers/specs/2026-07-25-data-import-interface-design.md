---
comet_change: add-data-import-interface
role: technical-design
canonical_spec: openspec
---

# Data Import Interface — Technical Design Doc

## 1. 概述

本文档是对 OpenSpec change `add-data-import-interface` 的深度技术设计，基于 open 阶段的 `proposal.md` / `design.md` / `specs/thematic-data-import/spec.md` / `tasks.md` 深化而成。

**目标**：通过 `POST /api/v1/data/import` HTTP API 支持 admin 用户远程上传三类专题模型数据（CSV / shapefile / .dat），自动完成校验、部署、触发离线计算，替代手工 SSH + Copy-Item 流程。

**canonical spec**：OpenSpec delta spec `openspec/changes/add-data-import-interface/specs/thematic-data-import/spec.md` 是需求事实源；本 Design Doc 是技术实现细化，不创建第二份需求 spec。

## 2. 模块架构

```
┌─────────────────────────────────────────────────────────────────┐
│  framework/api/routes/data_import.py  (Flask Blueprint)         │
│  POST /api/v1/data/import                                        │
│  - @jwt_required + admin 角色校验                                │
│  - 解析 multipart form (data_type + file)                       │
│  - 文件大小校验 (≤ 200MB)                                       │
│  - 临时保存到 tempfile                                           │
│  - 编排：校验 → 部署 → 触发 → 审计                               │
│  - 错误处理：400/403/413/500/504 + 回滚                         │
└────────┬────────────────────────────────────────────────────────┘
         │ 调用
    ┌────┴────┬────────────┬──────────────┬─────────────┐
    ▼         ▼            ▼              ▼             ▼
┌────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│validator│ │deployer│ │ trigger  │ │  audit   │ │  config  │
│        │ │        │ │          │ │ _logger  │ │          │
│ CSV    │ │ backup │ │ csv:     │ │          │ │ MAX_SIZE │
│ shape  │ │ deploy │ │  bulk_   │ │ logs/    │ │ TIMEOUT  │
│ .dat   │ │ clean  │ │  evaluate│ │ data_    │ │ TARGETS  │
│        │ │ restore│ │ shape:   │ │ import   │ │ BACKUP_  │
│        │ │        │ │  precomp │ │ .log     │ │ RETENTION│
│        │        │ │ dat:     │ │          │ │          │
│        │        │ │  check_  │ │          │ │          │
│        │        │ │  deploy  │ │          │ │          │
└────────┘ └────────┘ └────┬─────┘ └──────────┘ └──────────┘
                           │ 通过 adapter
                           ▼
              ┌─────────────────────────────┐
              │ framework/core_engine/      │
              │ adapter.py (CoreEngine)     │
              │ 新增 3 方法：               │
              │  - bulk_evaluate_csv()      │
              │  - precompute_stability()   │
              │  - check_grade_eval_deploy()│
              └────────────┬────────────────┘
                           │ 委托
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
   ┌────────────────┐ ┌──────────────┐ ┌──────────────────┐
   │ farmland_      │ │ farmland_    │ │ farmland_grade_  │
   │ diagnosis/     │ │ stability/   │ │ eval/            │
   │ evaluation.py  │ │ precompute.py│ │ runner.py        │
   │                │ │ 【新建】     │ │                  │
   │ bulk_evaluate()│ │ main()       │ │ FarmlandGrade    │
   │                │ │ g_to_records │ │ Runner.check_    │
   │                │ │              │ │ deployment()     │
   └────────────────┘ └──────────────┘ └──────────────────┘
                           │
                           ▼
              ┌─────────────────────────────┐
              │ farmland_stability/         │
              │ storage.py (StabilityStorage)│
              │ save_results() →            │
              │ data/farmland_stability/    │
              │ stability_results.db        │
              └─────────────────────────────┘
```

## 3. 关键技术决策

### 3.1 新建 precompute.py（填补现有空缺）

**问题**：`data/farmland_stability/README.md` 提到 `python -m src.ai_culti_demo.farmland_stability.precompute`，但该模块不存在。`run_all_models` 仅返回内存中的 GeoDataFrame `G`，不持久化；`StabilityStorage` 类已建好但从未与 `run_all_models` 接线。

**方案**：新建 `src/ai_culti_demo/farmland_stability/precompute.py`，封装完整流程：

```python
import os
from .model import run_all_models, save_final_results, MODULE_FIELDS, RESULT_CN
from .storage import StabilityStorage

def g_to_records(G, id_col='ID', region='PJFQ', score='ZHQZ', grade='GDZLDJ'):
    """将 GeoDataFrame G 转换为 StabilityStorage.save_results 期望的 records 列表"""
    records = []
    for _, row in G.iterrows():
        record = {
            'parcel_id': str(row[id_col]),
            'region': row.get(region),
            'score': row.get(score),
            'grade': row.get(grade),
        }
        all_results = {}
        for module_num, fields in MODULE_FIELDS.items():
            module_data = {}
            for f in fields:
                if f in row.index:
                    module_data[RESULT_CN.get(f, f)] = row[f]
            record[f'module_{module_num}'] = module_data
            all_results[f'module_{module_num}'] = module_data
        record['all_results'] = all_results
        records.append(record)
    return records

def main(shapefile_dir, manifest):
    """完整预计算流程：run_all_models → DB 持久化 → 文件输出"""
    current_file = os.path.join(shapefile_dir, manifest['current_filename'])
    history_files = [os.path.join(shapefile_dir, f) for f in manifest['history_filenames']]
    years = manifest['years']

    G = run_all_models(current_file, history_files, years)

    # DB 持久化
    storage = StabilityStorage()
    storage.create_tables()
    records = g_to_records(G)
    saved_count = storage.save_results(records)

    # 文件持久化（shapefile + xlsx，供在线查询重载）
    shp_file = os.path.join(shapefile_dir, 'stability_results.shp')
    xlsx_file = os.path.join(shapefile_dir, 'stability_results.xlsx')
    save_final_results(G, shp_file, xlsx_file, years)

    return {
        'status': 'ok',
        'processed': len(records),
        'saved_to_db': saved_count,
        'output_files': [shp_file, xlsx_file]
    }
```

**G → records 映射逻辑**：
- `MODULE_FIELDS`（来自 model.py）定义每个模块的字段列表，如 `{1: ['SAFE_ABS'], 2: ['BAL_ABS', 'BAL_REL'], ...}`
- `RESULT_CN`（来自 model.py）定义字段中文名映射，如 `{'SAFE_ABS': '等级边界安全度', ...}`
- 每个 record 的 `module_N` 字段是该模块所有字段值的字典（中文 key），`all_results` 汇总所有模块

**为什么 DB + 文件双持久化**：
- DB 路径：支持 `StabilityStorage.get_result(parcel_id)` 在线查询
- 文件路径：`save_final_results` 输出 shapefile + xlsx，支持 GIS 工具直接打开和在线查询重载 G

### 3.2 Adapter 扩展（3 个新方法）

在 `framework/core_engine/adapter.py` 的 `CoreEngine` 类中新增：

```python
def _ensure_data_import_imports(self):
    """延迟导入数据导入相关模块"""
    if not hasattr(self, '_data_import_ready'):
        from src.ai_culti_demo.farmland_diagnosis.evaluation import bulk_evaluate
        from src.ai_culti_demo.farmland_stability.precompute import main as precompute_main
        from src.ai_culti_demo.farmland_grade_eval.runner import FarmlandGradeRunner
        self._bulk_evaluate = bulk_evaluate
        self._precompute_main = precompute_main
        self._FarmlandGradeRunner = FarmlandGradeRunner
        self._data_import_ready = True

def bulk_evaluate_csv(self, csv_path: str) -> Dict[str, Any]:
    self._ensure_import()
    self._ensure_data_import_imports()
    try:
        return self._bulk_evaluate(csv_path)
    except Exception as e:
        return {"status": "error", "error": {"code": "BULK_EVALUATE_ERROR", "message": str(e)}}

def precompute_stability(self, shapefile_dir: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
    self._ensure_import()
    self._ensure_data_import_imports()
    try:
        return self._precompute_main(shapefile_dir, manifest)
    except Exception as e:
        return {"status": "error", "error": {"code": "PRECOMPUTE_ERROR", "message": str(e)}}

def check_grade_eval_deployment(self) -> Dict[str, Any]:
    self._ensure_import()
    self._ensure_data_import_imports()
    try:
        runner = self._FarmlandGradeRunner()
        result = runner.check_deployment()
        return {"deployment_ok": True, "detail": result} if result else {"deployment_ok": False, "detail": None}
    except Exception as e:
        return {"deployment_ok": False, "error": {"code": "DEPLOYMENT_CHECK_ERROR", "message": str(e)}}
```

**为什么用单独的 `_ensure_data_import_imports`**：避免在 `_ensure_import` 中引入 geopandas 等重依赖导致现有功能初始化失败；数据导入相关导入延迟到首次调用时。

### 3.3 触发器超时控制

```python
# framework/upload/data_trigger.py
import concurrent.futures
from framework.config import Config

def _run_with_timeout(func, *args, timeout=Config.DATA_IMPORT_TIMEOUT):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"触发超时（{timeout}s）")

def trigger_csv_evaluate(csv_path):
    from framework.core_engine.adapter import core_engine
    return _run_with_timeout(core_engine.bulk_evaluate_csv, csv_path)

def trigger_shapefile_precompute(target_dir, manifest):
    from framework.core_engine.adapter import core_engine
    return _run_with_timeout(core_engine.precompute_stability, target_dir, manifest)

def trigger_dat_check():
    from framework.core_engine.adapter import core_engine
    return _run_with_timeout(core_engine.check_grade_eval_deployment)
```

**为什么用 ThreadPoolExecutor 而非 signal.alarm**：signal.alarm 仅 Unix 可用，Windows 不支持；ThreadPoolExecutor 跨平台。

**超时后的清理**：超时后线程仍在后台运行（无法强制终止 Python 线程），但路由层会回滚文件部署并返回 504。后台线程完成后其结果被丢弃（无副作用，因 DB 写入幂等）。

### 3.4 部署 + 回滚事务性

```python
# framework/api/routes/data_import.py（伪代码）
def import_data():
    # ... 校验通过 ...
    backup_path = backup_existing(target_dir)  # Step 1: 备份
    try:
        deployed = deploy_* (src_path, target_dir)  # Step 2: 部署
        cleanup_backups(target_dir, keep=3)  # Step 3: 清理旧备份
        trigger_result = trigger_*(...)  # Step 4: 触发
        if trigger_result.get('status') == 'error':
            raise TriggerError(trigger_result)
    except (TimeoutError, TriggerError, Exception) as e:
        if backup_path:
            restored = restore_from_backup(target_dir)  # Step 5: 回滚
            if not restored:
                log_warning("回滚失败，需手动恢复")
        audit_log(success=False, message=str(e), restored_from_backup=True)
        return 500/504 + error
    audit_log(success=True, trigger_result=trigger_result)
    return 200 + response
```

**回滚边界**：
- 校验失败：不部署，不触发，不回滚（无需）
- 部署失败：已备份但部署未完成，从备份恢复
- 触发失败/超时：已部署，从备份恢复（覆盖新部署的文件）
- 回滚失败：记录警告，返回 500，提示手动恢复

### 3.5 DB 路径修正

| 模块 | design.md 原值（错误） | 实际路径 |
|------|----------------------|---------|
| 诊断 DB | `instance/farmland_diagnosis.db` | `data/farmland_diagnosis/farmland_diagnosis.db` |
| 稳定性 DB | `instance/farmland_stability.db` | `data/farmland_stability/stability_results.db` |

**来源**：
- `farmland_diagnosis/storage.py:11-13`：`db_dir = os.path.join(os.path.dirname(__file__), '../../data/farmland_diagnosis')` → `data/farmland_diagnosis/`，`db_path = os.path.join(db_dir, 'farmland_diagnosis.db')`
- `farmland_stability/storage.py:7`：`DEFAULT_DB_PATH = "data/farmland_stability/stability_results.db"`

### 3.6 CSV 部署文件名

上传的 CSV 文件无论原名是什么，部署时统一重命名为 `test.csv`（与 `data/farmland_diagnosis/README.md` 约定一致）。原文件名记录在审计日志中。

**理由**：`bulk_evaluate(input_csv)` 虽然接受任意路径，但 README、`batch_evaluate` 脚本、下游 `query_parcel` 等均默认读取 `test.csv`；保持一致避免破坏现有约定。

### 3.7 shapefile 字段校验时机

**上传阶段**：仅校验 zip 结构 + manifest + 文件组件完整性（.shp/.cpg/.dbf/.prj/.shx），不打开 shapefile。

**触发阶段**：`run_all_models` 内部调用 `require_columns(G, [id_col, region, score, grade] + LSD_COLS + QZ_COLS, '当前地块数据')`，缺失字段时抛 `ValueError`。触发器捕获后返回 400 + 缺失字段列表，并回滚部署。

**理由**：避免在校验阶段和触发阶段各打开一次 shapefile（geopandas.read_file 较慢）；字段校验交给单一事实源 `require_columns`。

## 4. 数据流

### 4.1 CSV 导入流程

```
admin POST /api/v1/data/import (data_type=csv, file=xxx.csv)
    ↓
[路由] JWT 校验 → admin 校验 → 文件大小校验
    ↓
[校验器] validate_csv(tmp_path):
    - pandas.read_csv (UTF-8 → GBK fallback)
    - 校验 14 必需列
    ↓ 校验失败 → 400
[部署器] backup_existing(data/farmland_diagnosis/) → backup/YYYYMMDD-HHMMSS/
        deploy_csv(tmp_path, target_dir) → 写入 test.csv
        cleanup_backups(keep=3)
    ↓
[触发器] trigger_csv_evaluate(test.csv):
    - adapter.bulk_evaluate_csv(test.csv)
    - bulk_evaluate 读取 CSV → 计算 → DiagnosisStorage.save_evaluation
    - 写入 data/farmland_diagnosis/farmland_diagnosis.db
    ↓ 触发失败 → 回滚 → 500
[审计] log_data_import(success=True, ...)
    ↓
200 + {status, data_type, deployed_path, backup_path, trigger_result}
```

### 4.2 shapefile 导入流程

```
admin POST /api/v1/data/import (data_type=shapefile, file=xxx.zip)
    ↓
[路由] JWT + admin + 大小校验
    ↓
[校验器] validate_shapefile_zip(tmp_path):
    - zipfile 校验总大小 ≤ 200MB、文件数 ≤ 30、无路径穿越
    - 解压到临时目录
    - 校验 manifest.json 字段完整
    - 校验每期 shapefile 5 组件齐全
    ↓ 校验失败 → 400
[部署器] backup_existing(data/farmland_stability/) → backup/YYYYMMDD-HHMMSS/
        deploy_shapefile(tmp_path, target_dir, manifest) → 解压内容到 target_dir
        cleanup_backups(keep=3)
    ↓
[触发器] trigger_shapefile_precompute(target_dir, manifest):
    - adapter.precompute_stability(target_dir, manifest)
    - precompute.main:
        a. run_all_models(current, history, years) → GeoDataFrame G
        b. g_to_records(G) → records 列表
        c. StabilityStorage.save_results(records) → data/farmland_stability/stability_results.db
        d. save_final_results(G, shp, xlsx, years) → stability_results.shp + .xlsx
    ↓ 触发失败 → 回滚 → 500
[审计] log_data_import(success=True, ...)
    ↓
200 + {status, data_type, deployed_files, backup_path, trigger_result}
```

### 4.3 .dat 导入流程

```
admin POST /api/v1/data/import (data_type=dat, file=xxx.dat)
    ↓
[路由] JWT + admin + 大小校验
    ↓
[校验器] validate_dat(tmp_path): 大小 > 0 且 ≤ 200MB
    ↓
[部署器] backup_existing(bin/farmland_quality_eval/) → backup/YYYYMMDD-HHMMSS/
        deploy_dat(tmp_path, target_dir) → 写入 Farmlands_Quality_Level_Database.dat
        cleanup_backups(keep=3)
    ↓
[触发器] trigger_dat_check():
    - adapter.check_grade_eval_deployment()
    - FarmlandGradeRunner.check_deployment() → 校验 exe + .dat 存在且可读
    ↓ 触发失败 → 回滚 → 500
[审计] log_data_import(success=True, ...)
    ↓
200 + {status, data_type, deployed_path, backup_path, trigger_result: {deployment_ok: true}}
```

## 5. 测试策略

### 5.1 单元测试

| 模块 | 测试文件 | 关键场景 |
|------|---------|---------|
| data_validator.py | tests/test_data_validator.py | CSV 缺列、GBK 编码、zip 缺 manifest、组件不完整、路径穿越、空 .dat |
| data_deployer.py | tests/test_data_deployer.py | 首次部署无备份、覆盖部署、备份保留 3 份、回滚成功/失败 |
| data_trigger.py | tests/test_data_trigger.py | 成功返回、返回错误字典、抛异常、超时（monkeypatch adapter） |
| audit_logger.py | tests/test_audit_logger.py | 日志字段完整性、成功/失败条目 |
| precompute.py | tests/test_precompute.py | g_to_records 转换正确性（mock GeoDataFrame）、main 完整流程（monkeypatch run_all_models） |

### 5.2 路由测试

`tests/test_data_import_route.py`：
- admin 成功上传三种类型
- 非 admin → 403
- 未携带 JWT → 401
- 缺 data_type → 400
- 缺文件 → 400
- 文件超限 → 413
- 校验失败 → 400
- 触发失败回滚 → 500
- 触发超时回滚 → 504

### 5.3 集成测试

`tests/test_data_import_integration.py`：使用真实临时目录 + mock adapter，端到端：
- CSV 上传 → 部署 → 触发 → 审计日志写入
- shapefile zip 上传 → 解压 → 部署 → 触发 → 审计日志写入
- .dat 上传 → 部署 → check_deployment → 审计日志写入
- 触发失败 → 回滚 → 审计日志记录回滚
- 备份保留策略：连续导入 4 次，验证 backup/ 下仅保留最近 3 份

### 5.4 测试约束

- **不实际启动 exe**：.dat 触发仅测 `check_deployment` 的 mock 返回
- **不依赖真实 shapefile 数据**：precompute 测试用 mock GeoDataFrame
- **不依赖真实 CSV 数据**：validator 测试用构造的小 CSV
- **monkeypatch adapter**：所有触发器测试 monkeypatch `core_engine` 方法，不实际调用 src/ai_culti_demo

## 6. Spec Patch（回写 delta spec）

### 6.1 修改 `specs/thematic-data-import/spec.md`

**修改 1**：`Shapefile Zip Validation` requirement 中补充字段校验时机说明
- 新增场景：`#### Scenario: 字段校验延迟到触发阶段`
- 说明：上传阶段仅校验文件组件完整性；字段级校验（LSD1-LSD12 等）由触发阶段 run_all_models 内置 require_columns 执行

**修改 2**：`Offline Computation Trigger` requirement 中细化 shapefile 触发结果
- 修改场景 `#### Scenario: shapefile 触发 run_all_models 成功`：trigger_result 应包含 `processed`（地块数）、`saved_to_db`（DB 写入数）、`output_files`（输出文件路径列表）

**修改 3**：`Data Deployment with Backup` requirement 中补充 CSV 重命名场景
- 新增场景：`#### Scenario: CSV 部署时重命名为 test.csv`

### 6.2 修改 `design.md`

- 修正 DB 路径：`instance/farmland_diagnosis.db` → `data/farmland_diagnosis/farmland_diagnosis.db`
- 修正 DB 路径：`instance/farmland_stability.db` → `data/farmland_stability/stability_results.db`
- 补充 precompute.py 说明

### 6.3 修改 `tasks.md`

- 新增任务组：`## 10. precompute.py 模块`
  - 10.1 创建 `src/ai_culti_demo/farmland_stability/precompute.py`
  - 10.2 实现 `g_to_records(G)` 转换函数
  - 10.3 实现 `main(shapefile_dir, manifest)` 完整流程
  - 10.4 编写 `tests/test_precompute.py`

## 7. 风险与缓解

| 风险 | 严重度 | 缓解 |
|------|--------|------|
| 大 CSV/shapefile 触发超 600s 超时 | 中 | 文档提示数据量上限；超时后回滚；后续可引入异步 |
| 回滚失败（磁盘错误等） | 低 | 记录警告 + 返回 500 + 提示手动恢复；备份目录仍在 |
| 并发导入文件冲突 | 低 | 文档提示"避免并发导入"；v1 不加锁 |
| precompute g_to_records 转换错误 | 中 | 单元测试覆盖；用 mock GeoDataFrame 验证字段映射 |
| shapefile 字段命名大小写不一致 | 低 | run_all_models 内置 require_columns 大小写敏感；失败返回缺失字段列表 |
| ThreadPoolExecutor 超时后线程泄漏 | 低 | 线程完成后自动退出；DB 写入幂等；接受短暂资源占用 |
| geopandas 依赖在 Windows 上的安装问题 | 低 | 上一轮已添加到 pyproject.toml 并验证可用 |

## 8. 开放问题

无未决问题。所有关键决策已通过 brainstorming 与用户确认。

## 9. 参考文件

- OpenSpec proposal: `openspec/changes/add-data-import-interface/proposal.md`
- OpenSpec design: `openspec/changes/add-data-import-interface/design.md`
- OpenSpec delta spec: `openspec/changes/add-data-import-interface/specs/thematic-data-import/spec.md`
- OpenSpec tasks: `openspec/changes/add-data-import-interface/tasks.md`
- 现有 adapter: `framework/core_engine/adapter.py`
- 现有稳定性模型: `src/ai_culti_demo/farmland_stability/model.py`
- 现有稳定性存储: `src/ai_culti_demo/farmland_stability/storage.py`
- 现有诊断模型: `src/ai_culti_demo/farmland_diagnosis/evaluation.py`
- 现有诊断存储: `src/ai_culti_demo/farmland_diagnosis/storage.py`
- 现有等级评价 runner: `src/ai_culti_demo/farmland_grade_eval/runner.py`
- 数据目录 README: `data/farmland_diagnosis/README.md`、`data/farmland_stability/README.md`、`bin/farmland_quality_eval/README.md`

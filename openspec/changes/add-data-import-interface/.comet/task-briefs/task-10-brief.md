# Task 10 Brief: 文档更新

> 本文件是 Task 10 的唯一需求来源。请先完整阅读本文件。

## 对应 tasks.md

第 8 节（8.1-8.5）

## 前置依赖

- ✅ Task 1-9 全部完成，`POST /api/v1/data/import` 已实现并测试通过（47/47 PASS）

## Files（允许修改）

- Modify: `data/farmland_diagnosis/README.md`（8.1）
- Modify: `data/farmland_stability/README.md`（8.2）
- Modify: `bin/farmland_quality_eval/README.md`（8.3）
- Modify: `docs/api.md`（8.4 — 在已有 API 文档中补充，不新建 `docs/api/data_import.md`）
- Modify: `README.md`（8.5 — 根 README 的 API 概览表）

## API 契约（文档内容来源）

### 端点
- **URL**: `POST /api/v1/data/import`
- **认证**: JWT + admin 角色（`Authorization: Bearer <token>`，非 admin 返回 403）
- **Content-Type**: `multipart/form-data`

### 请求字段
| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `data_type` | string | 是 | 数据类型：`csv` / `shapefile` / `dat` |
| `file` | file | 是 | 上传的文件 |

### 成功响应（200）
```json
{
    "status": "ok",
    "data": {
        "data_type": "csv",
        "deployed_path": "data/farmland_diagnosis/test.csv",
        "backup_path": "data/farmland_diagnosis/backup/20260725-110000",
        "trigger_result": {"status": "ok", "processed": 100, "errors": []}
    }
}
```

### 错误码
| HTTP 状态码 | 说明 |
|-------------|------|
| 400 | 缺少 data_type/file、data_type 不合法、校验失败（缺列/shapefile 组件不全/.dat 为空等） |
| 401 | 未携带 JWT |
| 403 | 非 admin 用户 |
| 413 | 文件大小超过 200MB |
| 500 | 触发器异常或返回错误字典（已自动回滚） |
| 504 | 触发器超时（600s，已自动回滚） |

### 数据类型说明

#### CSV（data_type=csv）
- 部署到 `data/farmland_diagnosis/test.csv`（固定文件名）
- 必需 14 列：`一级农业区`、`二级农业区`、`pH`、`有机质`、`有效磷`、`速效钾`、`容重`、`耕层质地`、`灌溉能力`、`排水能力`、`地形部位`、`质地构型`、`有效土层`、`耕层厚度`
- 编码：UTF-8（失败回退 GBK）
- 触发：`bulk_evaluate` 批量评价

#### shapefile（data_type=shapefile）
- 部署到 `data/farmland_stability/`（解压后扁平化）
- 上传格式：zip 包，含 `manifest.json` + 每期 shapefile 5 组件（.shp/.cpg/.dbf/.prj/.shx）
- manifest.json 格式：
  ```json
  {
      "current_year": 2024,
      "history_years": [2020, 2021],
      "years": [2020, 2021, 2024],
      "current_filename": "current.shp",
      "history_filenames": ["2020.shp", "2021.shp"]
  }
  ```
- zip 限制：文件数 ≤ 30、解压后总大小 ≤ 200MB、无路径穿越
- 触发：`precompute.main` 预计算 + 持久化

#### .dat（data_type=dat）
- 部署到 `bin/farmland_quality_eval/Farmlands_Quality_Level_Database.dat`（固定文件名）
- 校验：非空、≤ 200MB
- 触发：`FarmlandGradeRunner.check_deployment` 部署校验

### 其他
- 文件大小限制：200MB
- 触发超时：600 秒
- 备份策略：部署前备份现有文件到 `backup/YYYYMMDD-HHMMSS/`，保留最近 3 份
- 审计日志：`logs/data_import.log`（JSON 行格式）
- 触发失败自动回滚到备份

## 各文件更新要求

### 8.1 data/farmland_diagnosis/README.md

在文件末尾（或"部署方式"小节后）增加"通过 HTTP API 部署"小节：
- 说明 `POST /api/v1/data/import` + `data_type=csv` 用法
- 给出 curl 示例（登录获取 token + 上传 CSV）
- 列出 14 项必需列
- 说明部署后文件名为 `test.csv`，会触发 `bulk_evaluate` 批量评价

### 8.2 data/farmland_stability/README.md

在文件末尾（或"部署方式"小节后）增加"通过 HTTP API 部署"小节：
- 说明 `POST /api/v1/data/import` + `data_type=shapefile` 用法
- 给出 manifest.json 格式说明（5 个必需字段）
- 给出 zip 打包要求（manifest.json + 每期 5 组件）
- 给出 curl 示例
- 说明部署后触发 `precompute.main` 预计算

### 8.3 bin/farmland_quality_eval/README.md

在文件末尾增加"通过 HTTP API 部署"小节：
- 说明 `POST /api/v1/data/import` + `data_type=dat` 用法
- 给出 curl 示例
- 说明部署后文件名为 `Farmlands_Quality_Level_Database.dat`，会触发 `check_deployment` 校验

### 8.4 docs/api.md

在"县域诊断接口"小节之后、"错误码"小节之前，增加"数据导入接口"小节：
- 端点说明（POST /api/v1/data/import，需 admin 权限）
- 请求字段表（data_type + file）
- 三种数据类型说明（CSV 14 列 / shapefile zip + manifest / .dat）
- manifest.json 格式说明
- 成功响应示例
- 错误码表（补充 413 和 504）
- curl 示例（3 种类型各一个）
- 在文件末尾"错误码"表中补充 413 和 504

### 8.5 README.md（根）

在"API 概览"的"县域能力"表格之后，增加"数据导入"表格：
```markdown
### 数据导入

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/data/import` | 上传部署专题模型数据（CSV/shapefile/.dat，需 admin） |
```

同时将"功能特性"中的"15 个 REST API"更新为"16 个 REST API"。

## 执行步骤

1. 依次读取 5 个目标文件，理解现有结构
2. 按上述要求在合适位置插入新内容
3. 用 `git diff` 检查所有改动
4. 提交：
   ```
   git add data/farmland_diagnosis/README.md data/farmland_stability/README.md bin/farmland_quality_eval/README.md docs/api.md README.md
   git commit -m "docs: add data import API documentation (5 files updated)"
   ```

## 全局约束

- 不修改任何源代码文件（.py）
- 不修改任何测试文件
- 文档语言：中文
- curl 示例中的 URL 用 `http://localhost:5000`
- 保持各文件原有的风格和格式
- minimal edits：在现有文件中增加小节，不重写整个文件

## 风险信号自报项

1. 是否只修改了允许的 5 个文件？
2. 是否提交了不该提交的文件？
3. docs/api.md 是否在"错误码"表中补充了 413 和 504？
4. README.md 是否将"15 个 REST API"更新为"16 个"？
5. 三个 data README 是否都包含 curl 示例？

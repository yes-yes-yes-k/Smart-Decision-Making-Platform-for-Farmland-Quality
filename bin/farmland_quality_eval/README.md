# 耕地质量等级评价 exe 部署目录

本目录存放耕地质量等级和障碍度评价的 Fortran 可执行程序及其数据库。

## 部署文件

| 文件 | 说明 | 大小 |
|------|------|------|
| `Farmland_quality_evaluation.exe` | Fortran 编译的可执行程序 | ~911KB |
| `Farmlands_Quality_Level_Database.dat` | 评价指标数据库（二进制） | ~199KB |

## 数据来源

外部数据源：`F:\BaiduNetdiskDownload\耕地质量等级和障碍度\`

## 部署方式

exe 和 .dat 为二进制文件，已通过 `.gitignore` 排除，不入库。部署时需手动从外部数据源复制：

```powershell
$src = "F:\BaiduNetdiskDownload\耕地质量等级和障碍度"
$dst = "bin\farmland_quality_eval"
Copy-Item "$src\Farmland_quality_evaluation.exe" $dst -Force
Copy-Item "$src\Farmlands_Quality_Level_Database.dat" $dst -Force
```

## 调用契约

包装器 `src/ai_culti_demo/farmland_grade_eval/runner.py` 通过 `subprocess.Popen` 启动 exe：

- **stdin**：发送地块代码 + `\nquit\n`（GBK 编码）
- **stdout**：捕获评价结果文本（GBK 解码）
- **cwd**：设为本目录（exe 依赖同目录下的 .dat 文件）
- **超时**：默认 30 秒，超时后终止进程

## 启动时部署校验

系统启动时会调用 `FarmlandGradeRunner.check_deployment()` 校验：

- exe 文件存在
- .dat 数据库存在
- 文件可读

校验失败时返回 `status: "error"`，`error.code: "DEPLOYMENT_ERROR"`，阻止后续调用。

## 通过 HTTP API 部署

通过 `POST /api/v1/data/import` 接口上传 `.dat` 数据库文件，需 admin 权限。接口会将上传文件部署为本目录下的 `Farmlands_Quality_Level_Database.dat`（固定文件名），并自动触发 `FarmlandGradeRunner.check_deployment` 部署校验。

校验要求：文件非空、大小 ≤ 200MB。

### curl 示例

```bash
# 1. 登录获取 token（需 admin 账号）
curl -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 2. 上传 .dat 数据库（替换 <token>）
curl -X POST http://localhost:5000/api/v1/data/import \
  -H "Authorization: Bearer <token>" \
  -F "data_type=dat" \
  -F "file=@/path/to/Farmlands_Quality_Level_Database.dat"
```

部署成功后接口返回 `deployed_path` 与 `backup_path`，部署前会自动备份现有 `.dat` 文件到 `backup/YYYYMMDD-HHMMSS/`（保留最近 3 份）。触发 `check_deployment` 失败时会自动回滚到备份。

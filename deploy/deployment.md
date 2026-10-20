# 部署指南

耕地土壤酸化治理智能问答系统的生产环境部署文档。

## 架构概览

```
客户端
  ↓ HTTP:8000
waitress（WSGI 服务器，多线程并发）
  ↓
Flask 应用（production 配置）
  ↓
PostgreSQL/PostGIS + ChromaDB + SiliconFlow LLM
```

## 环境要求

| 组件     | 版本要求   | 说明                                      |
| ------ | ------ | --------------------------------------- |
| Python | ≥ 3.11 | scikit-learn 1.9 运行时要求 |
| PostgreSQL/PostGIS | PostgreSQL 14+ | 应用主数据库与空间查询 |
| NSSM   | 最新版    | Windows 服务管理（可选）                        |

## 部署步骤

### 1. 安装依赖

```bash
# 进入项目目录
cd d:\17417\Documents\agent_culti_demo

# 安装 Python 依赖（含 waitress）
pip install -e .
```

### 2. 配置环境变量

```powershell
# 复制环境变量模板
copy deploy\production.env.example .env
```

编辑 `.env` 文件，填写实际配置：

```ini
# 生成密钥（在 Python 中执行）
# python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=替换为随机生成的64位十六进制密钥
JWT_SECRET_KEY=替换为另一个随机生成的密钥

# PostgreSQL / PostGIS
DB_HOST=127.0.0.1
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=替换为数据库密码
DB_NAME=db_enterprise_qa

# SiliconFlow LLM
SILICONFLOW_API_KEY=sk-替换为实际API密钥
```

### 3. 初始化应用数据库表

```bash
python init_db.py
```

输出确认：

```
[初始化] 数据库表结构创建完成
[初始化] 管理员用户已创建: admin / admin123
[初始化] 普通用户已创建: user / user123
```

> 生产环境请立即修改默认密码。

### 4. 测试启动（前台模式）

```bash
python start_production_server.py
```

启动成功后访问 <http://127.0.0.1:8000/health> 确认服务状态：

```json
{"status": "ok", "service": "agent_culti_demo", "version": "1.3.0"}
```

常用启动参数：

| 参数                  | 默认值                 | 说明            |
| ------------------- | ------------------- | ------------- |
| `--host`            | 127.0.0.1           | 监听地址          |
| `--port`            | 8000                | 监听端口          |
| `--threads`         | 8                   | 工作线程数         |
| `--channel-timeout` | 120                 | 请求超时秒数        |
| `--log-level`       | INFO                | 日志级别          |
| `--log-file`        | logs/production.log | 日志文件路径        |
| `--init-db`         | -                   | 启动前初始化数据库表    |
| `--skip-check`      | -                   | 跳过生产配置校验（不推荐） |

### 4.1 生成前端底图瓦片（本地一张图）

前端地图底图使用项目自有的 GeoTIFF（`E:\Agent\一张图地图\China_RGB_500m_vis\China_RGB_500m_vis.tif`，500m/px，EPSG:3857），通过 GDAL 切片为 XYZ 瓦片金字塔后由 Nginx 静态托管。

#### 4.1.1 安装 GDAL

```powershell
# 方式 A：Miniforge3（推荐）
# 下载 Miniforge3-Windows-x86_64.exe（来自 https://github.com/conda-forge/miniforge/releases）
# 静默安装到 C:\Users\<User>\miniforge3 后：
& "C:\Users\<User>\miniforge3\Scripts\conda.exe" install -n base -c conda-forge gdal -y

# 方式 B：OSGeo4W64
# 下载 OSGeo4W 安装器并选择 gdal 包
```

校验：

```powershell
gdalinfo --version    # 应输出 GDAL 3.x
gdal2tiles --version  # 应输出 GDAL 3.x
```

#### 4.1.2 生成瓦片

```bash
# 默认参数（zoom 4-8，源 TIF 路径与输出目录已内置）
python scripts/generate_basemap_tiles.py --force

# 自定义参数
python scripts/generate_basemap_tiles.py --zoom 4-8 --processes 8 --force
```

输出至 `data/basemap_tiles/{z}/{x}/{y}.png`（约 383 MB，4680 张瓦片）。该目录已加入 `.gitignore`，不入版本库。

#### 4.1.3 Nginx 静态托管

`E:\Agent\nginx.conf` 端口 8008 server 块已配置：

```nginx
location /tiles/ {
    alias E:/Agent/agent_culti_demo/data/basemap_tiles/;
    expires 30d;
    add_header Cache-Control "public, immutable";
    add_header Access-Control-Allow-Origin * always;
    try_files $uri =404;
}
```

开发环境由 Flask `tiles_bp` Blueprint 直接服务 `/tiles/{z}/{x}/{y}.png`，Vite 已配置 `/tiles` 代理到 `http://127.0.0.1:5000`。

#### 4.1.4 源 TIF 更新流程

源 TIF 文件更新后需重新切片：

1. 替换 `E:\Agent\一张图地图\China_RGB_500m_vis\China_RGB_500m_vis.tif`
2. 运行 `python scripts/generate_basemap_tiles.py --force` 清理重建
3. 重启 Nginx（瓦片静态文件立即生效，无需 reload；长缓存由 expires 控制）
4. 前端浏览器强制刷新（Ctrl+F5）以丢弃旧瓦片缓存

> 若新源 TIF 非 EPSG:3857，加 `--reproject` 参数触发 `gdalwarp` 重投影。

### 4.2 生成广东高清底图瓦片（100m，叠加层）

在已有全国 500m 底图基础上，叠加广东 100m 高清底图层。源 TIF 为 `Guangdong_RGB_100m.tif`（Float64 Gray，100m/px，EPSG:3857，3.3 GB），需先预处理为 Byte RGB + 直方图匹配到全国图色调，再切片。

#### 4.2.1 安装预处理依赖

除 §4.1.1 的 GDAL 外，直方图匹配还需 rasterio + scikit-image：

```powershell
& "C:\Users\<User>\miniforge3\Scripts\conda.exe" install -n base -c conda-forge rasterio scikit-image -y
```

#### 4.2.2 预处理（Float64→Byte RGB + 直方图匹配）

```bash
# 默认直方图匹配（推荐，色调与全国图一致）
python scripts/prepare_gd_tif.py

# 跳过直方图匹配，用 2% 截断线性拉伸（色调可能略有差异）
python scripts/prepare_gd_tif.py --no-match-base
```

输出 `data/gd_tif_normalized.tif`（\~200 MB，Byte RGB，ColorInterp=Red/Green/Blue）。该文件已加入 `.gitignore`。

#### 4.2.3 生成瓦片

```bash
# 切片 zoom 4-11（100m/px 对应 zoom 11 为最高原生层级）
python scripts/generate_basemap_tiles.py --source data/gd_tif_normalized.tif --output data/gd_basemap_tiles --zoom 4-11 --force
```

输出至 `data/gd_basemap_tiles/{z}/{x}/{y}.png`（约 303 MB，3093 张瓦片）。该目录已加入 `.gitignore`。

#### 4.2.4 Nginx 静态托管

`nginx.conf` 端口 8008 server 块已配置：

```nginx
location /gd_tiles/ {
    alias E:/Agent/agent_culti_demo/data/gd_basemap_tiles/;
    expires 30d;
    add_header Cache-Control "public, immutable";
    add_header Access-Control-Allow-Origin * always;
    try_files $uri =404;
}
```

开发环境由 Flask `gd_tiles_bp` Blueprint 直接服务 `/gd_tiles/{z}/{x}/{y}.png`，Vite 已配置 `/gd_tiles` 代理到 `http://127.0.0.1:5000`。

#### 4.2.5 前端自动切换

前端 `mapConfig.js` 的 `addBaseLayers` 函数已实现自动切换逻辑：

- 地图中心在广东覆盖范围（108.99°E–118°E, 18.99°N–26°N）且 zoom ≥ 9 时，广东层 opacity=1

- 否则 opacity=0（隐藏，不发瓦片请求）

- 图层控件提供"广东高清底图"开关，用户可手动开关

#### 4.2.6 源 TIF 更新流程

1. 替换 `E:\Agent\一张图地图\China_RGB_500m_vis\Guangdong_RGB_100m\Guangdong_RGB_100m.tif`
2. 运行 `python scripts/prepare_gd_tif.py --force` 重新预处理
3. 运行 `python scripts/generate_basemap_tiles.py --source data/gd_tif_normalized.tif --output data/gd_basemap_tiles --zoom 4-11 --force` 清理重建
4. 前端浏览器强制刷新

### 5. 注册为 Windows 服务

#### 5.1 安装 NSSM

1. 从 <https://nssm.cc/download> 下载 NSSM
2. 将 `nssm.exe` 放入系统 PATH 或 `deploy\` 目录

#### 5.2 注册服务

以**管理员身份**运行 PowerShell：

```powershell
.\deploy\windows-service.ps1 install
```

#### 5.3 启动服务

```powershell
.\deploy\windows-service.ps1 start
```

#### 5.4 查看状态

```powershell
.\deploy\windows-service.ps1 status
```

输出示例：

```
========================================
服务名称:   AgentCultiDemo
显示名称:   耕地土壤酸化治理智能问答系统
当前状态:   Running
启动类型:   Automatic
日志文件:   logs\service.log
========================================
```

#### 5.5 查看实时日志

```powershell
Get-Content logs\service.log -Tail 50 -Wait
```

### 6. 验证部署

```powershell
# 健康检查
curl http://127.0.0.1:8000/health

# API 登录测试
curl -X POST http://127.0.0.1:8000/api/v1/auth/login `
  -H "Content-Type: application/json" `
  -d '{"username":"admin","password":"admin123"}'
```

### 7. SSE 流式输出反缓冲核对清单（必须）

> 目标：保证 `/chat/stream` 接口后端一产生 token / progress / heartbeat 事件，浏览器就立即收到，而不是被 Nginx / Vite / Waitress 中间层攒到 buffer 满再一次性下发。
> 如果以下任一条不满足，用户看到的效果会是"转圈 5\~30s，然后一次性吐出整段回答"。

**7.1 三层（浏览器 → 反向代理 → 后端）响应头检查**

从浏览器 DevTools → Network → 选中 `/chat/stream` → Headers，检查 Response Headers：

| Header               | 期望值                                                                   | 不满足时的修复                                                                  |
| -------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `Content-Type`       | 包含 `text/event-stream` 且 **必须有** **`charset=utf-8`**                  | 后端 chat.py 已补；若被 Nginx 覆盖需 `charset utf-8;` 或 `add_header` 覆盖            |
| `Cache-Control`      | 包含 `no-cache, no-transform`，推荐 `no-store, must-revalidate, max-age=0` | Flask/SSE 端点已设置；Nginx 侧再 `add_header ... always`                         |
| `X-Accel-Buffering`  | **必须是** **`no`**                                                      | 后端、Vite、Nginx 三处都要各自设置（见 7.2/7.3）                                        |
| 不能有 `Content-Length` | 响应头中**不要出现**，否则浏览器不会把它当流                                              | Nginx：`proxy_hide_header Content-Length;` 或 Flask 不用 `make_response` 强行塞 |
| `Transfer-Encoding`  | 通常是 `chunked`（HTTP/1.1）或不存在（HTTP/2）                                   | 关闭压缩、不塞 Content-Length 即可                                                |

**7.2 Nginx 层（如果用 Nginx 做 HTTPS / 域名）**

直接参考同目录 `nginx-sse-proxy.conf.example`，关键要点复列：

- [ ] `/api/v1/chat/stream` 放在通用 `/api/` 之前（Nginx 最长前缀匹配）

- [ ] `proxy_buffering off;` **这是第一优先级**

- [ ] `proxy_cache off;` `proxy_request_buffering off;`

- [ ] `proxy_set_header Accept-Encoding identity;`（不让后端压缩，压缩必须整块）

- [ ] `proxy_read_timeout 600s;`（否则长生成 LLM 会被 Nginx 主动断）

- [ ] `tcp_nodelay on;`（立即 flush，不攒 TCP 小包）

- [ ] `add_header X-Accel-Buffering "no" always;`（再叠加 CDN / 浏览器下游反缓冲）

**7.3 Vite dev proxy（开发态）**

`client/vite.config.js` 中 `/api/v1/chat/stream` 必须排在 `/api` 之前，且已设置：

- [x] `buffer: false`（关闭 Node http-proxy 内部攒包）

- [x] `proxyTimeout: 600000`、`timeout: 600000`

- [x] `proxyReq.setHeader('Accept-Encoding', 'identity')`

- [x] `res.setHeader('X-Accel-Buffering', 'no')`

- [x] `res.socket.setNoDelay(true)`

- [x] 遇到 SSE content-type 时 `delete proxyRes.headers['content-length']`

通用 `/api` 代理也要有相同兜底（防止以后新 SSE 接口漏配）。

**7.4 后端（Flask / Waitress）已实施项**

- [x] SSE 生成器被 `Response(stream_with_context(event_stream()), direct_passthrough=True)` 包装

- [x] 响应头：`Content-Type: text/event-stream; charset=utf-8`、`Cache-Control: no-cache, no-store, no-transform, must-revalidate, max-age=0`、`X-Accel-Buffering: no`

- [x] 阻塞阶段（prepare\_routed\_state / execute\_models / LLM init）有 `_run_blocking_with_heartbeat` 每 1 秒下发一次 heartbeat，避免 Nginx 断连

- [x] 所有路由分支（needs\_input / rag\_chat / boundary\_pending / function\_calling / execute\_models）都做到逐 token 或 8~~20 字符分块 + 15~~40ms 间隔流式下发

**7.5 一键验证脚本**

```bash
# 登录拿到 token（按实际环境改账号密码）
TOKEN=$(curl -s -X POST http://127.0.0.1:5000/api/v1/auth/login \
       -H 'Content-Type: application/json' \
       -d '{"username":"user","password":"user123"}' | python -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('access_token',''))")

# ⚠️ 关键：-N/--no-buffer 强制 curl 不做本地缓冲，-v 显示响应头
curl -N -v -X POST http://127.0.0.1:5000/api/v1/chat/stream \
     -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' \
     -H 'Accept: text/event-stream' \
     -d '{"conversation_id":"c1","message":"有机质含量解释一下","response_schema":"2.0","include_model_results":true}'
```

正确结果观察：

- 发起请求后 **1\~3 秒内**就出现第一行 `data: {"event":"init","..."}`（或 progress 事件），而不是等 20s 之后一起出现；

- 之后每几百毫秒就有一个 `event: token` / `event: progress` / `event: heartbeat` 增量行；

- 整个 LLM 生成期间 **curl 持续打印内容**；

- HTTP Status 为 200，响应头中含 `Content-Type: text/event-stream; charset=utf-8` 与 `X-Accel-Buffering: no`，**无** **`Content-Length`**。

如果第一行数据等了很久才出现 → 排查 后端阻塞阶段有没有 yield heartbeat / progress，或 Nginx proxy\_buffering 没关。
如果 token 是一大段一大段到达而不是持续到达 → 排查 LLM 上游流式、RAG chain 分块函数、或 Nginx `tcp_nodelay`。

## LangSmith 监控

生产环境默认启用 LangSmith 追踪，可视化多智能体全链路执行。

### 配置

`.env` 文件中已包含 LangSmith 配置（见 `deploy/production.env.example`）：

| 环境变量                   | 说明                    | 默认值                               |
| ---------------------- | --------------------- | --------------------------------- |
| `LANGCHAIN_TRACING_V2` | tracing 开关（`true` 启用） | `true`（生产环境）                      |
| `LANGCHAIN_API_KEY`    | LangSmith API Key     | 需填写                               |
| `LANGCHAIN_ENDPOINT`   | LangSmith API 端点      | `https://api.smith.langchain.com` |
| `LANGCHAIN_PROJECT`    | LangSmith 项目名称        | `agent-culti-demo`                |

### 查看 Trace

1. 登录 [LangSmith 平台](https://smith.langchain.com)
2. 进入项目 `agent-culti-demo`
3. 查看每次 `/api/v1/chat/` 请求的完整 trace，包括：

   - LangGraph 各节点执行顺序和耗时

   - 专业智能体调用详情

   - LLM 调用的 token 用量和响应延迟

   - RAG 检索的召回结果和耗时

### 关闭 Tracing

如需临时关闭 tracing（如调试或性能测试）：

```ini
# .env 中注释或删除
# LANGCHAIN_TRACING_V2=true
```

## 服务管理速查

```powershell
.\deploy\windows-service.ps1 install    # 安装服务
.\deploy\windows-service.ps1 uninstall  # 卸载服务
.\deploy\windows-service.ps1 start      # 启动服务
.\deploy\windows-service.ps1 stop       # 停止服务
.\deploy\windows-service.ps1 restart    # 重启服务
.\deploy\windows-service.ps1 status     # 查看状态
```

## 日志位置

| 日志类型 | 路径                           |
| ---- | ---------------------------- |
| 应用日志 | `logs/production.log`        |
| 服务日志 | `logs/service.log`（NSSM 重定向） |

## 故障排查

### 启动失败：配置校验不通过

```
[错误] 生产环境配置校验失败，缺失以下必需环境变量:
  - SECRET_KEY
```

**解决**：检查 `.env` 文件是否已创建且包含所有必需变量。

### PostgreSQL 连接失败

```
sqlalchemy.exc.OperationalError: connection refused
```

**解决**：

1. 确认 PostgreSQL 已启动，目标数据库已创建并启用 PostGIS。
2. 核对 `.env` 中 `DB_HOST`、`DB_PORT`、`DB_USER`、`DB_PASSWORD` 和 `DB_NAME`。
3. 使用同一账号执行 `python init_db.py` 验证建表权限。

### Windows 服务启动后立即停止

**解决**：

1. 查看 `logs/service.log` 获取错误信息
2. 确认 Python 路径正确：`Get-Command python`
3. 确认 NSSM 注册的路径无误
4. 尝试前台运行 `python start_production_server.py` 排查启动错误

### ChromaDB 向量库初始化失败

**解决**：

1. 确认 `chroma_db/` 目录有写入权限
2. 如果从开发环境迁移，确认 `chroma_db/` 目录已完整复制
3. 首次部署可删除 `chroma_db/` 目录让程序自动重建

### LangSmith tracing 不生效

**解决**：

1. 确认 `.env` 中 `LANGCHAIN_TRACING_V2=true`
2. 确认 `LANGCHAIN_API_KEY` 已填写有效值
3. 确认 `.env` 文件被加载（`start_production_server.py` 和 `start_http_server.py` 均已调用 `load_dotenv()`）
4. 检查网络是否能访问 `https://api.smith.langchain.com`
5. 未设置 API Key 时 tracing 静默关闭，不会报错——这是正常行为

## 安全清单

- [ ] `.env` 文件已创建且不在版本控制中（已在 `.gitignore` 排除）

- [ ] SECRET\_KEY 和 JWT\_SECRET\_KEY 使用随机生成的强密钥

- [ ] `instance/production.db` 数据库文件已创建且定期备份

- [ ] SILICONFLOW\_API\_KEY 已配置

- [ ] 默认密码 admin/admin123 已修改

- [ ] 防火墙仅放行所需端口（默认 8000）

- [ ] 日志文件定期轮转（NSSM 已配置日志轮转）

## 目录结构

```
deploy/
├── production.env.example      # 环境变量模板
├── windows-service.ps1         # Windows 服务管理脚本
└── deployment.md               # 本文档
```

## 相关文件

- 启动脚本：[start\_production\_server.py](../start_production_server.py)

- 应用配置：[framework/config.py](../framework/config.py)

- 数据库初始化：[init\_db.py](../init_db.py)

- OpenAPI 规范：[docs/openapi.json](../docs/openapi.json)


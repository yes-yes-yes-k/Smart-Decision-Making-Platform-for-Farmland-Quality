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
SQLite + ChromaDB + SiliconFlow LLM
```

## 环境要求

| 组件 | 版本要求 | 说明 |
|------|---------|------|
| Python | ≥ 3.10 | 与开发环境一致 |
| SQLite | 内置 | 无需单独安装，数据库文件位于 `instance/production.db` |
| NSSM | 最新版 | Windows 服务管理（可选） |

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

# 数据库使用 SQLite，无需额外配置
# 数据库文件自动创建于 instance/production.db

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

启动成功后访问 http://127.0.0.1:8000/health 确认服务状态：
```json
{"status": "ok", "service": "agent_culti_demo", "version": "1.3.0"}
```

常用启动参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--host` | 127.0.0.1 | 监听地址 |
| `--port` | 8000 | 监听端口 |
| `--threads` | 8 | 工作线程数 |
| `--channel-timeout` | 120 | 请求超时秒数 |
| `--log-level` | INFO | 日志级别 |
| `--log-file` | logs/production.log | 日志文件路径 |
| `--init-db` | - | 启动前初始化数据库表 |
| `--skip-check` | - | 跳过生产配置校验（不推荐） |

### 5. 注册为 Windows 服务

#### 5.1 安装 NSSM

1. 从 https://nssm.cc/download 下载 NSSM
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

| 日志类型 | 路径 |
|---------|------|
| 应用日志 | `logs/production.log` |
| 服务日志 | `logs/service.log`（NSSM 重定向） |

## 故障排查

### 启动失败：配置校验不通过

```
[错误] 生产环境配置校验失败，缺失以下必需环境变量:
  - SECRET_KEY
```

**解决**：检查 `.env` 文件是否已创建且包含所有必需变量。

### 数据库文件访问失败

```
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) unable to open database file
```

**解决**：
1. 确认 `instance/` 目录存在且有写入权限
2. 首次部署运行 `python init_db.py` 自动创建目录和数据库文件
3. 如果从开发环境迁移，可将 `instance/development.db` 复制为 `instance/production.db`

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

## 安全清单

- [ ] `.env` 文件已创建且不在版本控制中（已在 `.gitignore` 排除）
- [ ] SECRET_KEY 和 JWT_SECRET_KEY 使用随机生成的强密钥
- [ ] `instance/production.db` 数据库文件已创建且定期备份
- [ ] SILICONFLOW_API_KEY 已配置
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

- 启动脚本：[start_production_server.py](../start_production_server.py)
- 应用配置：[framework/config.py](../framework/config.py)
- 数据库初始化：[init_db.py](../init_db.py)
- OpenAPI 规范：[docs/openapi.json](../docs/openapi.json)

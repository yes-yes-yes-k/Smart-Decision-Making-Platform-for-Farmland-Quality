# Windows 服务管理脚本
# 基于 NSSM (Non-Sucking Service Manager) 将应用注册为 Windows 服务
#
# 前置条件:
#   1. 下载 NSSM: https://nssm.cc/download
#   2. 将 nssm.exe 放入 PATH 或本脚本同目录
#   3. 以管理员权限运行 PowerShell
#
# 用法:
#   .\deploy\windows-service.ps1 install   # 安装为 Windows 服务
#   .\deploy\windows-service.ps1 uninstall # 卸载服务
#   .\deploy\windows-service.ps1 start     # 启动服务
#   .\deploy\windows-service.ps1 stop      # 停止服务
#   .\deploy\windows-service.ps1 restart   # 重启服务
#   .\deploy\windows-service.ps1 status    # 查看状态

param(
    [Parameter(Position=0)]
    [ValidateSet("install", "uninstall", "start", "stop", "restart", "status")]
    [string]$Action = "status"
)

$ErrorActionPreference = "Stop"

# === 配置 ===
$ServiceName = "AgentCultiDemo"
$ServiceDisplayName = "耕地土壤酸化治理智能问答系统"
$ServiceDescription = "集成 RAG、Function Calling 和多智能体架构的统一框架 API 服务"

$ProjectRoot = Resolve-Path "$PSScriptRoot\.."
$PythonExe = (Get-Command python).Source
$EntryScript = Join-Path $ProjectRoot "start_production_server.py"
$LogFile = Join-Path $ProjectRoot "logs\service.log"
$WorkDir = $ProjectRoot

# === 辅助函数 ===
function Find-Nssm {
    $nssm = Get-Command nssm -ErrorAction SilentlyContinue
    if ($nssm) { return $nssm.Source }

    $localNssm = Join-Path $PSScriptRoot "nssm.exe"
    if (Test-Path $localNssm) { return $localNssm }

    return $null
}

function Test-Administrator {
    $current = [Security.Principal.WindowsPrincipal]::new(
        [Security.Principal.WindowsIdentity]::GetCurrent()
    )
    return $current.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

# === 主逻辑 ===
if (-not (Test-Administrator)) {
    Write-Host "[错误] 需要以管理员权限运行此脚本" -ForegroundColor Red
    Write-Host "  右键 PowerShell -> 以管理员身份运行" -ForegroundColor Yellow
    exit 1
}

# 确保 logs 目录存在
$logDir = Split-Path $LogFile -Parent
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

switch ($Action) {
    "install" {
        $nssm = Find-Nssm
        if (-not $nssm) {
            Write-Host "[错误] 未找到 nssm.exe" -ForegroundColor Red
            Write-Host "  请从 https://nssm.cc/download 下载并放到 PATH 或 deploy\ 目录" -ForegroundColor Yellow
            exit 1
        }

        # 检查是否已安装
        $existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if ($existing) {
            Write-Host "[警告] 服务 '$ServiceName' 已存在，请先卸载" -ForegroundColor Yellow
            exit 1
        }

        Write-Host "[安装] 正在注册 Windows 服务: $ServiceName" -ForegroundColor Cyan

        & $nssm install $ServiceName $PythonExe $EntryScript
        & $nssm set $ServiceName DisplayName $ServiceDisplayName
        & $nssm set $ServiceName Description $ServiceDescription
        & $nssm set $ServiceName AppDirectory $WorkDir
        & $nssm set $ServiceName AppStdout $LogFile
        & $nssm set $ServiceName AppStderr $LogFile
        & $nssm set $ServiceName AppRotateFiles 1
        & $nssm set $ServiceName AppRotateOnline 1
        & $nssm set $ServiceName AppRotateSeconds 86400
        & $nssm set $ServiceName AppRotateBytes 10485760

        # 自动重启策略
        & $nssm set $ServiceName AppExit Default Restart
        & $nssm set $ServiceName AppRestartDelay 5000

        # 启动类型: 自动
        & $nssm set $ServiceName Start SERVICE_AUTO_START

        Write-Host "[完成] 服务已安装" -ForegroundColor Green
        Write-Host ""
        Write-Host "后续操作:" -ForegroundColor Cyan
        Write-Host "  启动: .\deploy\windows-service.ps1 start"
        Write-Host "  状态: .\deploy\windows-service.ps1 status"
        Write-Host "  日志: Get-Content $LogFile -Tail 50 -Wait"
    }

    "uninstall" {
        $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if (-not $svc) {
            Write-Host "[警告] 服务 '$ServiceName' 不存在" -ForegroundColor Yellow
            exit 0
        }

        if ($svc.Status -eq "Running") {
            Write-Host "[停止] 正在停止服务..." -ForegroundColor Cyan
            Stop-Service -Name $ServiceName -Force
        }

        Write-Host "[卸载] 正在移除服务..." -ForegroundColor Cyan
        $nssm = Find-Nssm
        if ($nssm) {
            & $nssm remove $ServiceName confirm
        } else {
            sc.exe delete $ServiceName
        }

        Write-Host "[完成] 服务已卸载" -ForegroundColor Green
    }

    "start" {
        $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if (-not $svc) {
            Write-Host "[错误] 服务 '$ServiceName' 不存在，请先安装" -ForegroundColor Red
            exit 1
        }
        if ($svc.Status -eq "Running") {
            Write-Host "[提示] 服务已在运行" -ForegroundColor Yellow
            exit 0
        }
        Write-Host "[启动] 正在启动服务..." -ForegroundColor Cyan
        Start-Service -Name $ServiceName
        Start-Sleep -Seconds 2
        $svc = Get-Service -Name $ServiceName
        if ($svc.Status -eq "Running") {
            Write-Host "[完成] 服务已启动" -ForegroundColor Green
        } else {
            Write-Host "[错误] 服务启动失败，查看日志: $LogFile" -ForegroundColor Red
            exit 1
        }
    }

    "stop" {
        $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if (-not $svc) {
            Write-Host "[错误] 服务 '$ServiceName' 不存在" -ForegroundColor Red
            exit 1
        }
        if ($svc.Status -ne "Running") {
            Write-Host "[提示] 服务未在运行" -ForegroundColor Yellow
            exit 0
        }
        Write-Host "[停止] 正在停止服务..." -ForegroundColor Cyan
        Stop-Service -Name $ServiceName -Force
        Write-Host "[完成] 服务已停止" -ForegroundColor Green
    }

    "restart" {
        $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if (-not $svc) {
            Write-Host "[错误] 服务 '$ServiceName' 不存在" -ForegroundColor Red
            exit 1
        }
        Write-Host "[重启] 正在重启服务..." -ForegroundColor Cyan
        Restart-Service -Name $ServiceName -Force
        Start-Sleep -Seconds 2
        Write-Host "[完成] 服务已重启" -ForegroundColor Green
    }

    "status" {
        $svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
        if (-not $svc) {
            Write-Host "[状态] 服务 '$ServiceName' 未安装" -ForegroundColor Yellow
            Write-Host "  安装: .\deploy\windows-service.ps1 install"
            exit 0
        }

        $statusColor = switch ($svc.Status) {
            "Running" { "Green" }
            "Stopped" { "Red" }
            default   { "Yellow" }
        }

        Write-Host "========================================" -ForegroundColor Cyan
        Write-Host "服务名称:   $ServiceName"
        Write-Host "显示名称:   $ServiceDisplayName"
        Write-Host "当前状态:   " -NoNewline
        Write-Host "$($svc.Status)" -ForegroundColor $statusColor
        Write-Host "启动类型:   $($svc.StartType)"
        Write-Host "日志文件:   $LogFile"
        Write-Host "========================================" -ForegroundColor Cyan

        if ($svc.Status -eq "Running") {
            Write-Host ""
            Write-Host "查看实时日志:" -ForegroundColor Cyan
            Write-Host "  Get-Content $LogFile -Tail 50 -Wait"
        }
    }
}

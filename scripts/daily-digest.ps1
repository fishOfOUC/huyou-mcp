# 每日跑一次「校友动态」摘要并通过 QQ 邮箱推送。
# 计划任务里调用本脚本（带 --no-send 则只采集不发信）。

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$logDir = Join-Path $root "data"
$log = Join-Path $logDir "digest.log"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Location $root

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"[$stamp] 开始抓取" | Out-File -FilePath $log -Append -Encoding utf8

try {
    $output = & $python -m huyou_mcp.cli digest 2>&1
    $output | Out-File -FilePath $log -Append -Encoding utf8
    "[$((Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))] 完成" | Out-File -FilePath $log -Append -Encoding utf8
} catch {
    "[$((Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))] 失败: $_" | Out-File -FilePath $log -Append -Encoding utf8
    exit 1
}

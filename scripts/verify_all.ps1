<#
一個指令做完驗證：啟動測試站 → 等 /login 回應 → 60 組畫面檢查 → 完整測試 → 整理成 summary.md → 關掉測試站。
用法（在任何位置都可以）：
  powershell -NoProfile -ExecutionPolicy Bypass -File D:\democase\_worktrees\ai-wt-ux\scripts\verify_all.ps1
可選參數：
  -Name 名稱        輸出資料夾名稱（預設用時間）
  -Port 埠號        測試站埠號（預設 5121，避開 5097 公開站與 5111）
  -SkipLayout       不跑畫面檢查
  -SkipTests        不跑完整測試
結果在 D:\democase\ai\logs\verify\<名稱>\summary.md
#>
param(
    [string]$Name = (Get-Date -Format "yyyyMMdd-HHmmss"),
    [int]$Port = 5122,
    [switch]$SkipLayout,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = "D:\democase\ai\.venv\Scripts\python.exe"
$out = "D:\democase\ai\logs\verify\$Name"
New-Item -ItemType Directory -Force -Path $out | Out-Null
Set-Location $root

# 同一個埠已經有程式在用或被系統保留，自動挑選下一個可用埠
while ($Port -lt 5300) {
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
        $listener.Start()
        $listener.Stop()
        break
    } catch {
        $Port++
    }
}

$server = $null
try {
    $env:DEMO_PORT = "$Port"
    $server = Start-Process -FilePath $python -ArgumentList "-X", "utf8", "scripts\run_demo.py" `
        -WorkingDirectory $root -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "$out\server.log" -RedirectStandardError "$out\server-error.log"

    # 最多等 60 秒，一旦就緒立刻開始，沒有回應才放棄
    $ready = $false
    for ($i = 0; $i -lt 30 -and -not $ready; $i++) {
        Start-Sleep -Seconds 2
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/login" -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { $ready = $true }
        } catch {
            $_.Exception.Message | Out-File -Append -Encoding UTF8 "$out\probe-errors.log"
        }
    }
    if (-not $ready) {
        "沒有啟動成功（60 秒內 /login 沒有回應），看 server-error.log" | Set-Content -Encoding UTF8 "$out\server_ok.txt"
        & $python -X utf8 scripts\verify_summary.py $out
        exit 3
    }
    "正常（埠 $Port，/login 回應 200）" | Set-Content -Encoding UTF8 "$out\server_ok.txt"

    if (-not $SkipLayout) {
        $p = Start-Process -FilePath $python -ArgumentList "-X", "utf8", "scripts\check_layout_widths.py", "http://127.0.0.1:$Port", "$out\layout" `
            -WorkingDirectory $root -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput "$out\layout.log" -RedirectStandardError "$out\layout-error.log"
        # 畫面檢查最多 20 分鐘，超過就中止
        if (-not $p.WaitForExit(1200000)) { taskkill /PID $p.Id /T /F | Out-Null }
    }

    if (-not $SkipTests) {
        $p = Start-Process -FilePath $python -ArgumentList "-X", "utf8", "-m", "pytest", "-q", "-p", "no:cacheprovider", "--basetemp=D:/democase/ai/logs/test-runs/verify-$Name" `
            -WorkingDirectory $root -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput "$out\pytest.txt" -RedirectStandardError "$out\pytest-error.log"
        # 完整測試最多 30 分鐘
        if (-not $p.WaitForExit(1800000)) { taskkill /PID $p.Id /T /F | Out-Null }
    }

    & $python -X utf8 scripts\verify_summary.py $out
}
finally {
    # 不論成功或失敗，一定關掉自己開的測試站（連同子程序）
    if ($server) { taskkill /PID $server.Id /T /F 2>$null | Out-Null }
}

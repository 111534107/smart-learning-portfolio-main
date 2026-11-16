# AI 會議室系統啟動與停止

本文件記錄本機 AI 會議室使用的 8765 埠號操作指令。

## 強制停止 8765

在 PowerShell 執行：

```powershell
$pids = Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique

if ($pids) {
  Stop-Process -Id $pids -Force
  Write-Host "已強制停止 8765：$($pids -join ', ')"
} else {
  Write-Host "找不到占用 8765 的程序"
}
```

確認埠號已釋放：

```powershell
Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
```

沒有輸出就代表 8765 已停止。

## 啟動 AI 會議室

### 確認使用 8765（避免誤啟動到 8766）

會議室會讀取環境變數 `MEETING_ROOM_PORT`。如果目前瀏覽器開的是 `8766`，先在同一個 PowerShell 視窗執行：

```powershell
$env:MEETING_ROOM_PORT
```

若顯示 `8766`，改回 8765：

```powershell
$env:MEETING_ROOM_PORT = "8765"
```

或清除環境變數，使用程式預設的 8765：

```powershell
Remove-Item Env:MEETING_ROOM_PORT -ErrorAction SilentlyContinue
```

啟動後，瀏覽器網址必須和埠號一致：

```text
正式本機會議室：http://127.0.0.1:8765/
測試用埠號（若明確指定）：http://127.0.0.1:8766/
```

在 PowerShell 執行：

```powershell
Start-Process `
  -FilePath python `
  -ArgumentList "server.py" `
  -WorkingDirectory "D:\democase\ai-meeting-room" `
  -WindowStyle Hidden
```

等待 2 秒後確認服務：

```powershell
Start-Sleep -Seconds 2
Invoke-WebRequest http://127.0.0.1:8765/ -UseBasicParsing
```

若回應 `StatusCode : 200`，用瀏覽器開啟：

```text
http://127.0.0.1:8765/
```

## 需要查看啟動錯誤時

不要使用 `-WindowStyle Hidden`，直接在專案目錄執行：

```powershell
Set-Location "D:\democase\ai-meeting-room"
python server.py
```

確認服務啟動後按 `Ctrl+C` 會停止前景程序。

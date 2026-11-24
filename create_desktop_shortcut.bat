@echo off
chcp 65001 >nul
setlocal EnableExtensions
rem 在桌面建立「資管科學習歷程」捷徑，指向本資料夾的 start_system.bat（資料夾搬家後重新執行一次即可）
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$desktop = [Environment]::GetFolderPath('Desktop');" ^
  "$link = Join-Path $desktop ([string][char]0x8CC7 + [char]0x7BA1 + [char]0x79D1 + [char]0x5B78 + [char]0x7FD2 + [char]0x6B77 + [char]0x7A0B + '.lnk');" ^
  "$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut($link);" ^
  "$shortcut.TargetPath = (Join-Path (Get-Location) 'start_system.bat');" ^
  "$shortcut.WorkingDirectory = (Get-Location).Path;" ^
  "$shortcut.IconLocation = \"$env:SystemRoot\System32\shell32.dll,13\";" ^
  "$shortcut.Save();" ^
  "Write-Host ('OK: ' + $link)"
if errorlevel 1 (
    echo [錯誤] 建立捷徑失敗。也可以直接對 start_system.bat 按右鍵 → 傳送到 → 桌面（建立捷徑）。
    pause
    exit /b 1
)
echo 已在桌面建立捷徑「資管科學習歷程」，之後點它就能啟動系統。
pause

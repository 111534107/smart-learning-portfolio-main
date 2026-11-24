@echo off
chcp 65001 >nul
setlocal EnableExtensions
rem 資管科學習歷程：一鍵啟動（MySQL → 虛擬環境 → .env → 資料庫 → Flask → 瀏覽器）
rem 全部用相對位置，clone 到任何資料夾都能用。說明見 docs\05_交接與專案管理\組員開啟說明.md
cd /d "%~dp0"
title 資管科學習歷程

rem ---- 0. 先拉最新版（只做快轉；有本機修改或沒網路時略過，照現有版本啟動）----
if exist ".git" (
    where git >nul 2>nul && (
        echo 檢查是否有新版本...
        git pull --ff-only || echo [注意] 無法自動更新，先用目前版本啟動。
    )
)

rem ---- 1. 找 Python ----
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [錯誤] 找不到 Python。請到 https://www.python.org/downloads/ 安裝 Python 3.12 或 3.13，
    echo        安裝時勾選「Add python.exe to PATH」，裝好後重新執行。
    goto :fail
)

rem ---- 2. 找 XAMPP 並啟動 MySQL ----
if defined XAMPP_HOME if exist "%XAMPP_HOME%\mysql\bin\mysqld.exe" goto :xampp_found
for %%D in (C D E F G) do (
    if exist "%%D:\xampp\mysql\bin\mysqld.exe" (
        set "XAMPP_HOME=%%D:\xampp"
        goto :xampp_found
    )
)
echo [錯誤] 找不到 XAMPP（已找過 C: 到 G: 的 \xampp）。
echo        請先安裝 XAMPP：https://www.apachefriends.org/
echo        若裝在別的位置，先在此視窗執行 set XAMPP_HOME=你的XAMPP資料夾 再執行本檔，
echo        或在系統環境變數新增 XAMPP_HOME。
goto :fail

:xampp_found
echo XAMPP：%XAMPP_HOME%
"%XAMPP_HOME%\mysql\bin\mysqladmin.exe" -u root -h 127.0.0.1 -P 3306 --connect-timeout=2 ping >nul 2>nul
if not errorlevel 1 (
    echo MySQL 已在執行。
    goto :mysql_ready
)
echo 正在啟動 MySQL...
start "XAMPP MySQL" /min "%XAMPP_HOME%\mysql\bin\mysqld.exe" --defaults-file="%XAMPP_HOME%\mysql\bin\my.ini" --standalone
set /a TRIES=0
:wait_mysql
"%XAMPP_HOME%\mysql\bin\mysqladmin.exe" -u root -h 127.0.0.1 -P 3306 --connect-timeout=2 ping >nul 2>nul
if not errorlevel 1 goto :mysql_ready
set /a TRIES+=1
if %TRIES% geq 30 (
    echo [錯誤] MySQL 30 秒內沒有啟動。請打開 XAMPP Control Panel 按 MySQL 的 Start，
    echo        看紅字訊息；常見原因是 3306 埠被另一套 MySQL 占用。
    goto :fail
)
ping -n 2 127.0.0.1 >nul
goto :wait_mysql

:mysql_ready

rem ---- 3. 第一次執行：建立虛擬環境並安裝套件 ----
if not exist ".venv\Scripts\python.exe" (
    echo 第一次執行：建立虛擬環境 .venv ...
    %PY% -m venv .venv
    if errorlevel 1 goto :fail
)
rem requirements.txt 有變動（或還沒裝過）才重新安裝
fc /b requirements.txt ".venv\requirements.installed" >nul 2>nul
if errorlevel 1 (
    echo 安裝套件中（第一次約需幾分鐘）...
    ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 (
        echo [錯誤] 套件安裝失敗，請檢查網路後重新執行。
        goto :fail
    )
    copy /y requirements.txt ".venv\requirements.installed" >nul
)

rem ---- 4. 第一次執行：從範例建立 .env ----
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo 已從 .env.example 建立 .env
)

rem ---- 5. 建資料庫、跑遷移、啟動系統並開瀏覽器 ----
".venv\Scripts\python.exe" scripts\start_local.py
if errorlevel 1 goto :fail
goto :eof

:fail
echo.
echo 啟動失敗，請依上面的訊息處理，或看 docs\05_交接與專案管理\組員開啟說明.md 的常見問題。
pause
exit /b 1

@echo off
chcp 65001 >nul
title CareGift 2.0 FastAPI Server

echo ========================================================
echo   CareGift 2.0 智慧關懷送禮平台 - 後端伺服器啟動中
echo   介接技術：FastAPI + RAG 醫學知識庫 + CWA 中央氣象署
echo ========================================================
echo.

cd /d "%~dp0backend"
echo [1/2] 檢查 Python 環境...
python --version
if errorlevel 1 (
    echo [錯誤] 找不到 Python，請確認已安裝 Python 並加入 PATH 環境變數。
    pause
    exit /b
)

echo.
echo [2/2] 正在啟動 FastAPI 後端伺服器 (Port: 8000)...
echo 後端 API 規格文件請造訪：https://giftsensevjbu.onrender.com/docs
echo.
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

pause

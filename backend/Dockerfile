# ========================================================
# CareGift 2.0 - Python FastAPI Backend Dockerfile
# ========================================================
FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 設定環境變數
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 複製依賴檔案並安裝
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製後端所有檔案與資料庫
COPY . .

# 暴露 FastAPI 埠號
EXPOSE 8000

# 啟動 FastAPI 服務（綁定 0.0.0.0 確保容器外部可正常存取）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

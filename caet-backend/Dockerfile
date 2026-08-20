# ============================================================
# CAET 后端镜像：FastAPI + Uvicorn
# 启动先执行 db_init（幂等建表/建库/seed/建管理员），再起服务。
# ============================================================
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/uploads

EXPOSE 8000

CMD ["sh", "-c", "python -m app.db_init && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

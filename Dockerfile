# 使用指定的 Python Image
FROM python:3.8-slim-bullseye

# 設定工作目錄
WORKDIR /app

RUN apt-get update && apt-get install -y \
    g++ \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# 複製整個專案到容器中
COPY . .

# 安装套件
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Flask Port
EXPOSE 62593

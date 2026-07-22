FROM python:3.11-slim

WORKDIR /app

# 安装系统基础工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY openbb_agent_bridge.py /app/openbb_agent_bridge.py

EXPOSE 32001

ENTRYPOINT ["python", "openbb_agent_bridge.py"]

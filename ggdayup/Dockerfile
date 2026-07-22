FROM python:3.11-slim

WORKDIR /app

# 安装系统工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 拷贝项目源码并安装本地 OpenBB 及其扩展（包含 akshare 两融扩展）
COPY . /app/openbb_source

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir openbb openbb-platform-api openbb-mcp-server yfinance pandas requests akshare && \
    pip install --no-cache-dir -e /app/openbb_source/openbb_platform/providers/akshare && \
    pip install --no-cache-dir -e /app/openbb_source/openbb_platform/extensions/equity && \
    pip install --no-cache-dir -e /app/openbb_source/openbb_platform/extensions/platform_api && \
    python -c "from openbb_core.app.static.package_builder import PackageBuilder; PackageBuilder().build()"

# 拷贝自定义配置文件
COPY ggdayup/user_settings.json /root/.openbb_platform/user_settings.json

ENV PYTHONUNBUFFERED=1
ENV OPENBB_PLATFORM_API_HOST=0.0.0.0
ENV OPENBB_PLATFORM_API_PORT=6900

EXPOSE 6900

ENTRYPOINT ["openbb-api", "--host", "0.0.0.0", "--port", "6900"]


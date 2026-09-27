# syntax=docker/dockerfile:1

# 运行时锁定 Python 3.12
FROM python:3.12-slim AS base
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

# 测试阶段：判据测试不过则镜像构建失败
FROM base AS test
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY pyproject.toml conftest.py ./
COPY tests ./tests
RUN python -m pytest -q && touch /tmp/tests-passed

# 交付镜像：默认构建即会经过测试阶段
FROM base AS runtime
COPY --from=test /tmp/tests-passed /tmp/tests-passed
RUN useradd --create-home bridge
USER bridge
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

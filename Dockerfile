# 单阶段构建：前端 dist 已预先构建好（frontend/dist）
# 镜像源说明：fnOS 等 NAS 默认加速器（docker.fnnas.com）可能返回 401 导致无法构建，
#   这里直接指定可用镜像源主机名，绕过 NAS 的 registry-mirror 劫持。
#   若你的网络可直连 Docker Hub，可改回官方源：
#   docker build --build-arg PYTHON_IMAGE=python:3.12-slim .
# 需要完整从源码构建前端时，使用 Dockerfile.full
ARG PYTHON_IMAGE=docker.1ms.run/library/python:3.12-slim
FROM ${PYTHON_IMAGE}
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY backend/ ./
COPY frontend/dist /frontend/dist

ENV DATA_DIR=/data
RUN mkdir -p /data/images
VOLUME ["/data"]

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

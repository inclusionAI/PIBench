#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "===== [1/5] 构建前端 (litemall-vue) ====="
cd litemall-vue
npm install
npm run build
echo "前端构建完成"

echo "===== [2/5] 复制前端产物到后端 static 目录 ====="
mkdir -p ../litemall-all/src/main/resources/static/vue/
cp -r dist/* ../litemall-all/src/main/resources/static/vue/
cd "$SCRIPT_DIR"
echo "前端产物已复制"

echo "===== [3/5] Maven 构建 ====="
mvn clean package -DskipTests
echo "Maven 构建完成"

echo "===== [4/5] 复制 jar 到 docker 目录并启动容器 ====="
cp litemall-all/target/litemall-all-*-exec.jar docker/litemall/litemall.jar
cd docker
docker compose down 2>/dev/null || true
docker compose build --no-cache
docker compose up -d
cd "$SCRIPT_DIR"

echo "===== [5/5] 等待服务就绪 ====="
echo "等待服务启动 (最多60秒)..."
for i in $(seq 1 12); do
    sleep 5
    if curl -sf http://localhost:9080/vue/index.html > /dev/null 2>&1; then
        echo "服务启动成功！(用时约 ${i}0 秒)"
        echo "前端页面: http://localhost:9080/vue/index.html"
        exit 0
    fi
    echo "  等待中... (${i}0秒)"
done

echo "服务启动超时，请检查日志: docker logs litemall-app"
exit 1

#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== BookCars 一键构建启动 ==="

HOST_IP="${HOST_IP:-localhost}"

# 自动从 .env.docker.example 生成 .env.docker（替换 localhost:4002 → HOST_IP:8102）
generate_env() {
  local svc=$1
  local src="./$svc/.env.docker.example"
  local dst="./$svc/.env.docker"
  if [ ! -f "$dst" ]; then
    if [ ! -f "$src" ]; then
      echo "错误: $src 不存在"; exit 1
    fi
    echo "  从 $src 生成 $dst ..."
    sed "s|http://localhost:4002|http://${HOST_IP}:8102|g" "$src" > "$dst"
  else
    echo "  $dst 已存在，跳过"
  fi
}

echo "--- 检查/生成环境配置 ---"
generate_env "backend"
generate_env "admin"
generate_env "frontend"

echo "--- 构建并启动容器（首次 build 约 3-5 分钟）---"
docker compose -p bcpreauth down --remove-orphans 2>/dev/null || true
docker compose -p bcpreauth up --build -d

echo ""
echo "等待服务启动..."

MAX_WAIT=120
INTERVAL=5
ELAPSED=0
BACKEND_READY=false
FRONTEND_READY=false

while [ $ELAPSED -lt $MAX_WAIT ]; do
  sleep $INTERVAL
  ELAPSED=$((ELAPSED + INTERVAL))

  if [ "$BACKEND_READY" = false ] && curl -sf http://localhost:8102/api/settings > /dev/null 2>&1; then
    BACKEND_READY=true
    echo "  [${ELAPSED}s] 后端就绪 (port 8102)"
  fi

  if [ "$FRONTEND_READY" = false ] && curl -sf http://localhost:8104/ > /dev/null 2>&1; then
    FRONTEND_READY=true
    echo "  [${ELAPSED}s] 前端就绪 (port 8104)"
  fi

  if [ "$BACKEND_READY" = true ] && [ "$FRONTEND_READY" = true ]; then
    break
  fi

  echo "  [${ELAPSED}s] 等待中..."
done

echo ""
echo "=== 服务状态 ==="
if [ "$FRONTEND_READY" = true ]; then
  echo "  前端:        http://localhost:8104/"
else
  echo "  前端:        未就绪"
fi
if [ "$BACKEND_READY" = true ]; then
  echo "  后端 API:    http://localhost:8102/api/settings"
else
  echo "  后端 API:    未就绪"
fi
echo "  Admin 面板:  http://localhost:8103/"
echo "  MongoDB:     localhost:8100"
echo "  Mongo Express: http://localhost:8101/"
echo ""
echo "  管理员账号:  admin@bookcars.ma / B00kC4r5"
echo ""

if [ "$BACKEND_READY" = true ] && [ "$FRONTEND_READY" = true ]; then
  echo "所有服务启动成功！"

  # Seed demo data (idempotent - skips if data already exists)
  echo ""
  echo "--- Seeding demo data ---"
  MONGO_URI="mongodb://admin:admin@localhost:27017/bookcars?authSource=admin"
  docker cp "$SCRIPT_DIR/seed.js" bcpreauth-mongo-1:/seed.js
  docker exec bcpreauth-mongo-1 mongosh "$MONGO_URI" --quiet --file /seed.js

  # Create placeholder images in CDN volume
  docker cp "$SCRIPT_DIR/seed-images.sh" bcpreauth-bc-backend-1:/tmp/seed-images.sh
  docker exec bcpreauth-bc-backend-1 sh /tmp/seed-images.sh
else
  echo "部分服务未就绪，请检查日志: docker compose -p bcpreauth logs"
  exit 1
fi

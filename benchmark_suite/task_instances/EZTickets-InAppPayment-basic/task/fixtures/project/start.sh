#!/bin/bash
set -e

docker compose up --build -d

echo "等待后端和数据库启动..."
for i in $(seq 1 60); do
  if docker compose exec -T backend curl -sf http://backend:3331/api/v1/health > /dev/null 2>&1; then
    echo "服务启动成功"
    docker compose ps
    exit 0
  fi
  sleep 2
done

echo "服务启动失败"
docker compose ps
docker compose logs --tail=200
exit 1

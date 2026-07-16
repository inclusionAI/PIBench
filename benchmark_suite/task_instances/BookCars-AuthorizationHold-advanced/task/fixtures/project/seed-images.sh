#!/bin/sh
# Create placeholder images in CDN volume for seed data
# Run after containers are up: docker exec <backend> bash /bookcars/seed-images.sh
CDN=/var/www/cdn/bookcars
mkdir -p $CDN/users $CDN/cars $CDN/locations $CDN/licenses

# 1x1 PNG placeholder (valid minimal PNG)
PLACEHOLDER=$(printf "\\x89PNG\\r\\n\\x1a\\n\\x00\\x00\\x00\\rIHDR\\x00\\x00\\x00\\x01\\x00\\x00\\x00\\x01\\x08\\x02\\x00\\x00\\x00\\x90wS\\xde\\x00\\x00\\x00\\x0cIDATx\\x9cc\\xf8\\x0f\\x00\\x00\\x01\\x01\\x00\\x05\\x18\\xd8N\\x00\\x00\\x00\\x00IEND\\xaeB\\x60\\x82")

for f in supplier_avatar.png driver_avatar.png; do
  [ ! -f "$CDN/users/$f" ] && printf "%b" "$PLACEHOLDER" > "$CDN/users/$f"
done
for f in car_corolla.png car_duster.png car_mercedes.png; do
  [ ! -f "$CDN/cars/$f" ] && printf "%b" "$PLACEHOLDER" > "$CDN/cars/$f"
done
echo "CDN placeholders ready"

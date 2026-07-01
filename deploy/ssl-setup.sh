#!/usr/bin/env bash
set -euo pipefail

DOMAIN="api.syroce.com"
EMAIL="${1:?Kullanim: ./ssl-setup.sh email@adresiniz.com}"

echo "=== SSL Sertifika Kurulumu: $DOMAIN ==="

if ! command -v certbot &>/dev/null; then
    echo "[1/3] Certbot kuruluyor..."
    apt-get update -qq
    apt-get install -y -qq certbot
else
    echo "[1/3] Certbot zaten kurulu"
fi

mkdir -p /var/www/certbot

echo "[2/3] Nginx gecici olarak durduruluyor (port 80 icin)..."
docker compose -f docker-compose.production.yml stop nginx 2>/dev/null || true

echo "[3/3] Let's Encrypt sertifikasi aliniyor..."
certbot certonly \
    --standalone \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    -d "$DOMAIN" \
    --preferred-challenges http

echo ""
echo "=== Sertifika basariyla alindi ==="
echo "Sertifika yolu: /etc/letsencrypt/live/$DOMAIN/"
echo ""

CRON_JOB="0 3 * * 0 certbot renew --quiet --deploy-hook 'docker compose -f $(pwd)/docker-compose.production.yml restart nginx'"
if ! crontab -l 2>/dev/null | grep -q "certbot renew"; then
    (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
    echo "Otomatik yenileme cron job eklendi (her Pazar 03:00)"
else
    echo "Otomatik yenileme cron job zaten mevcut"
fi

echo ""
echo "Simdi docker compose'u baslatin:"
echo "  docker compose -f docker-compose.production.yml up -d"

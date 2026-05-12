#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DOMAIN="api.syroce.com"

# Script-relative compose path: hem `bash deploy/deploy.sh` hem
# `cd deploy && bash deploy.sh` çalışır.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$SCRIPT_DIR/docker-compose.production.yml}"
cd "$REPO_ROOT"

log()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[HATA]${NC} $1"; }
info() { echo -e "${BLUE}[*]${NC} $1"; }

echo ""
echo "============================================"
echo "  Syroce PMS Production Deployment"
echo "  Domain: $DOMAIN"
echo "============================================"
echo ""

# ── 1. Sistem Gereksinimleri ──
info "1/7 - Sistem gereksinimleri kontrol ediliyor..."

if ! command -v docker &>/dev/null; then
    info "Docker kuruluyor..."
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable docker
    systemctl start docker
    log "Docker kuruldu"
else
    log "Docker zaten kurulu: $(docker --version)"
fi

if ! docker compose version &>/dev/null; then
    err "Docker Compose plugin bulunamadi!"
    exit 1
fi
log "Docker Compose: $(docker compose version --short)"

# ── 2. Dizin Yapisi ──
info "2/7 - Dizin yapisi hazirlaniyor..."
mkdir -p backups
mkdir -p /var/www/certbot
log "Dizinler hazir"

# ── 3. .env Kontrolu ──
info "3/7 - Ortam degiskenleri kontrol ediliyor..."
if [ ! -f .env ]; then
    err ".env dosyasi bulunamadi!"
    echo ""
    echo "  Adimlar:"
    echo "  1. cp .env.production.example .env"
    echo "  2. nano .env  (degerleri doldurun)"
    echo "  3. Bu scripti tekrar calistirin"
    echo ""
    exit 1
fi

source .env

REQUIRED_VARS=("DB_NAME" "JWT_SECRET" "CORS_ORIGINS" "CM_CREDENTIAL_KEY" "CM_MASTER_KEY_CURRENT")
MISSING=()
for var in "${REQUIRED_VARS[@]}"; do
    val="${!var:-}"
    if [ -z "$val" ] || [[ "$val" == *"BURAYA"* ]]; then
        MISSING+=("$var")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    err "Asagidaki degiskenler eksik veya doldurulmamis:"
    for m in "${MISSING[@]}"; do
        echo "  - $m"
    done
    exit 1
fi
log "Ortam degiskenleri tamam"

# ── 4. SSL Kontrolu ──
info "4/7 - SSL sertifikasi kontrol ediliyor..."
if [ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
    warn "SSL sertifikasi bulunamadi!"
    echo ""
    echo "  Once SSL sertifikasini alin:"
    echo "  sudo ./ssl-setup.sh email@adresiniz.com"
    echo ""
    echo "  SSL olmadan devam etmek istiyor musunuz? (sadece test icin)"
    read -p "  [e/H]: " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Ee]$ ]]; then
        exit 1
    fi
    warn "SSL olmadan devam ediliyor (SADECE TEST!)"

    mkdir -p /etc/letsencrypt/live/$DOMAIN
    openssl req -x509 -nodes -days 1 -newkey rsa:2048 \
        -keyout /etc/letsencrypt/live/$DOMAIN/privkey.pem \
        -out /etc/letsencrypt/live/$DOMAIN/fullchain.pem \
        -subj "/CN=$DOMAIN" 2>/dev/null
    warn "Self-signed sertifika olusturuldu (gecici)"
else
    log "SSL sertifikasi mevcut"
fi

# ── 5. Build ──
info "5/7 - Docker imajlari build ediliyor..."
docker compose -f "$COMPOSE_FILE" build --no-cache
log "Build tamamlandi"

# ── 6. Deploy ──
info "6/7 - Servisler baslatiliyor..."
docker compose -f "$COMPOSE_FILE" up -d
log "Servisler baslatildi"

# ── 7. Dogrulama ──
info "7/7 - Deployment dogrulaniyor..."
echo ""

sleep 10

check_service() {
    local name=$1
    local check=$2
    if eval "$check" &>/dev/null; then
        log "$name: AKTIF"
        return 0
    else
        err "$name: BASARISIZ"
        return 1
    fi
}

PASS=0
FAIL=0

check_service "MongoDB" "docker compose -f "$COMPOSE_FILE" exec -T mongo mongosh --eval 'db.adminCommand(\"ping\")' --quiet" && ((PASS++)) || ((FAIL++))
check_service "Redis" "docker compose -f "$COMPOSE_FILE" exec -T redis redis-cli ping" && ((PASS++)) || ((FAIL++))
check_service "Backend" "docker compose -f "$COMPOSE_FILE" exec -T backend curl -sf http://localhost:8001/api/health/liveness" && ((PASS++)) || ((FAIL++))

sleep 5

check_service "Nginx (HTTP)" "curl -sf http://localhost/health" && ((PASS++)) || ((FAIL++))
check_service "HTTPS" "curl -sf -k https://$DOMAIN/api/health/liveness" && ((PASS++)) || ((FAIL++))

echo ""
echo "============================================"
echo "  DEPLOYMENT SONUCU"
echo "============================================"
echo ""
echo -e "  Basarili: ${GREEN}$PASS${NC}"
echo -e "  Basarisiz: ${RED}$FAIL${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    log "TUM SERVISLER AKTIF!"

    # Tek-komutlu rollback için son başarılı imaj tag'ini kaydet.
    # deploy/rollback.sh bu dosyadan okuyarak önceki sürüme döner.
    LAST_GOOD_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d_%H%M%S)}"
    echo "$LAST_GOOD_TAG" > deploy/.last_good_tag
    log "Last-good tag kaydedildi: $LAST_GOOD_TAG (deploy/.last_good_tag)"

    echo ""
    echo "  API URL:      https://$DOMAIN"
    echo "  Health:       https://$DOMAIN/api/health/liveness"
    echo "  Callback:     https://$DOMAIN/api/integrations/hotelrunner/callback"
    echo "  Webhook:      https://$DOMAIN/api/integrations/hotelrunner/webhook"
    echo ""
    echo "  Loglar:       docker compose -f "$COMPOSE_FILE" logs -f backend"
    echo "  Durdurma:     docker compose -f "$COMPOSE_FILE" down"
    echo "  Rollback:     bash deploy/rollback.sh"
    echo ""
else
    err "Bazi servisler baslatilmadi!"
    echo "  Loglari inceleyin:"
    echo "  docker compose -f "$COMPOSE_FILE" logs"
fi

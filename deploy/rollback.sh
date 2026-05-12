#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Syroce PMS — Tek Komutlu Rollback (Git-Based Rebuild)
# ──────────────────────────────────────────────────────────────────────
# `deploy/docker-compose.production.yml` `build:` direktifi kullanır
# (image registry tag'leri yok). Bu yüzden rollback aslında bir
# **git checkout + rebuild + restart** işlemidir; tag = commit SHA.
#
# Kullanım (HER ZAMAN repo root'tan koşulur):
#   bash deploy/rollback.sh                # last_good_tag commit'ine dön
#   bash deploy/rollback.sh abc1234        # belirli commit SHA'ya dön
#   bash deploy/rollback.sh --list         # son 10 commit'i listele
#   bash deploy/rollback.sh --resume       # önceki başarısız rollback'i sürdür
#   bash deploy/rollback.sh --dry-run      # ne yapacağını göster, çalıştırma
#
# Ön koşullar:
#   * git repo (working tree clean önerilir; uncommit'li değişiklik
#     stash'lenir, sonunda geri uygulanmaz — operatöre bildirilir)
#   * deploy/.last_good_tag — deploy.sh başarılı çalışınca yazılır
#   * docker compose çalışır
#   * deploy/smoke.sh (rollback sonrası otomatik koşar)
#
# Exit kodları:
#   0  → Rollback başarılı + smoke PASS
#   1  → Smoke FAIL / build FAIL / pull FAIL
#   2  → Kullanım hatası / ön koşul yok
# ──────────────────────────────────────────────────────────────────────

set -uo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
err()   { echo -e "${RED}[FAIL]${NC} $1"; }
info()  { echo -e "${BLUE}[*]${NC} $1"; }
step()  { echo -e "\n${CYAN}── $1 ──${NC}"; }

# Script-relative: hem `bash deploy/rollback.sh` hem `cd deploy && bash rollback.sh`
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

LAST_GOOD_FILE="${LAST_GOOD_FILE:-$SCRIPT_DIR/.last_good_tag}"
ROLLBACK_FROM_FILE="${LAST_GOOD_FILE}.rollback_from"
COMPOSE_FILE="${COMPOSE_FILE:-$SCRIPT_DIR/docker-compose.production.yml}"
SMOKE_SCRIPT="${SMOKE_SCRIPT:-$SCRIPT_DIR/smoke.sh}"
DRY_RUN=0
LIST_ONLY=0
RESUME=0
TARGET_TAG=""

for arg in "$@"; do
    case "$arg" in
        --dry-run)  DRY_RUN=1 ;;
        --list)     LIST_ONLY=1 ;;
        --resume)   RESUME=1 ;;
        --help|-h)
            sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        --*)
            err "Bilinmeyen seçenek: $arg"
            exit 2
            ;;
        *)
            TARGET_TAG="$arg"
            ;;
    esac
done

cd "$REPO_ROOT"

echo "════════════════════════════════════════════════════════════"
echo "  Syroce PMS — Rollback (git-based rebuild)"
echo "  Repo root     : $REPO_ROOT"
echo "  Compose       : $COMPOSE_FILE"
echo "  Last-good file: $LAST_GOOD_FILE"
[ "$DRY_RUN" = "1" ] && warn "DRY-RUN modu — hiçbir komut çalıştırılmaz"
echo "════════════════════════════════════════════════════════════"

# ── List mode ──────────────────────────────────────────────────────
if [ "$LIST_ONLY" = "1" ]; then
    step "Son 10 commit (rollback adayı)"
    if ! command -v git &>/dev/null; then
        err "git komutu yok"
        exit 2
    fi
    git log --oneline -10 || warn "git log başarısız"
    echo ""
    if [ -f "$LAST_GOOD_FILE" ]; then
        info "Kayıtlı last_good_tag: $(cat "$LAST_GOOD_FILE")"
    else
        warn "$LAST_GOOD_FILE yok — deploy.sh hiç başarıyla koşmamış olabilir"
    fi
    if [ -f "$ROLLBACK_FROM_FILE" ]; then
        warn "Önceki başarısız rollback bulundu (.rollback_from): $(cat "$ROLLBACK_FROM_FILE")"
        info "Sürdürmek için: bash deploy/rollback.sh --resume"
    fi
    exit 0
fi

# ── Hedef tag çözümleme (--resume önceliği var) ────────────────────
step "1/5 — Hedef commit belirleniyor"

if [ "$RESUME" = "1" ]; then
    if [ ! -f "$ROLLBACK_FROM_FILE" ]; then
        err "Sürdürülecek bir rollback yok ($ROLLBACK_FROM_FILE bulunamadı)"
        exit 2
    fi
    TARGET_TAG="$(cat "$ROLLBACK_FROM_FILE" | tr -d '[:space:]')"
    info "--resume: önceki başarısız rollback'i sürdürüyorum: $TARGET_TAG"
elif [ -n "$TARGET_TAG" ]; then
    info "Komut satırından: $TARGET_TAG"
elif [ -f "$LAST_GOOD_FILE" ]; then
    TARGET_TAG="$(cat "$LAST_GOOD_FILE" | tr -d '[:space:]')"
    if [ -z "$TARGET_TAG" ]; then
        err "$LAST_GOOD_FILE boş"
        exit 2
    fi
    info "$LAST_GOOD_FILE'den okundu: $TARGET_TAG"
else
    err "Hedef yok: $LAST_GOOD_FILE bulunamadı ve argüman geçilmedi"
    echo ""
    echo "  Çözüm:"
    echo "    bash deploy/rollback.sh --list           # mevcut commit'leri gör"
    echo "    bash deploy/rollback.sh abc1234           # commit'i el ile geç"
    exit 2
fi

# ── Ön koşul kontrolü ──────────────────────────────────────────────
step "2/5 — Ön koşullar"

for cmd in git docker; do
    if ! command -v "$cmd" &>/dev/null; then
        err "$cmd komutu yok"
        exit 2
    fi
done
ok "git + docker mevcut"

if ! docker compose version &>/dev/null; then
    err "Docker Compose plugin yok"
    exit 2
fi
ok "Docker Compose mevcut"

if [ ! -f "$COMPOSE_FILE" ]; then
    err "Compose dosyası yok: $COMPOSE_FILE"
    exit 2
fi
ok "Compose dosyası: $COMPOSE_FILE"

# Hedef commit gerçekten var mı?
if ! git cat-file -e "${TARGET_TAG}^{commit}" 2>/dev/null; then
    err "Commit bulunamadı: $TARGET_TAG"
    info "Önce git fetch yapın: git fetch --all --tags"
    exit 2
fi
ok "Hedef commit doğrulandı: $TARGET_TAG"

# Working tree temiz mi?
DIRTY=0
if ! git diff --quiet || ! git diff --cached --quiet; then
    DIRTY=1
    warn "Working tree kirli — değişiklikler stash'lenecek (rollback sonrası elle geri al)"
fi

# Şu anki commit (rollback öncesi sidecar'a yazılır)
CURRENT_COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

# ── Rollback yürütme ───────────────────────────────────────────────
step "3/5 — Git: $CURRENT_COMMIT → $TARGET_TAG"

if [ "$DRY_RUN" = "0" ]; then
    # Önce sidecar yaz (build/up FAIL olursa --resume desteği için)
    echo "$TARGET_TAG" > "$ROLLBACK_FROM_FILE"

    if [ "$DIRTY" = "1" ]; then
        STASH_NAME="rollback-$(date +%s)"
        if git stash push -u -m "$STASH_NAME" >/dev/null 2>&1; then
            ok "Stash: $STASH_NAME (sonra: git stash pop)"
        else
            err "Stash başarısız — manuel temizleyin"
            exit 1
        fi
    fi

    if ! git checkout "$TARGET_TAG"; then
        err "git checkout $TARGET_TAG başarısız"
        exit 1
    fi
    ok "Checkout tamam"
fi

# ── Build + up + smoke ─────────────────────────────────────────────
step "4/5 — Docker rebuild + restart"

CMDS=(
    "docker compose -f \"$COMPOSE_FILE\" build --no-cache"
    "docker compose -f \"$COMPOSE_FILE\" up -d"
)

for cmd in "${CMDS[@]}"; do
    echo "  $ $cmd"
    if [ "$DRY_RUN" = "0" ]; then
        if ! eval "$cmd"; then
            err "Komut başarısız: $cmd"
            err "Sistem yarı-rollback durumunda. --resume ile sürdürebilirsiniz."
            exit 1
        fi
    fi
done

if [ "$DRY_RUN" = "0" ]; then
    ok "Servisler $TARGET_TAG ile yeniden başlatıldı"
    sleep 8
fi

# ── Smoke ──────────────────────────────────────────────────────────
step "5/5 — Rollback sonrası smoke"

if [ ! -f "$SMOKE_SCRIPT" ]; then
    warn "Smoke script yok ($SMOKE_SCRIPT) — manuel doğrulama yapın"
    exit 0
fi

if [ "$DRY_RUN" = "1" ]; then
    info "DRY-RUN: smoke atlanıyor — komut: bash $SMOKE_SCRIPT"
    exit 0
fi

if bash "$SMOKE_SCRIPT"; then
    ok "Rollback + smoke PASS"
    echo "$TARGET_TAG" > "$LAST_GOOD_FILE"
    rm -f "$ROLLBACK_FROM_FILE"
    exit 0
else
    err "Rollback YAPILDI ama smoke FAIL — last_good_tag güncellenmedi"
    err "Önceki commit: $CURRENT_COMMIT"
    err "Yeniden denemek için: bash deploy/rollback.sh --resume"
    exit 1
fi

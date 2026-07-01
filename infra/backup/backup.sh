#!/usr/bin/env bash
# =====================================================================
# Syroce PMS - Offsite Yedekleme Servisi (mongodump -> S3)
# ---------------------------------------------------------------------
# Bu script kucuk bir yedekleme konteyneri olarak surekli calisir.
# Her gun BACKUP_TIME (varsayilan 03:00) saatinde MongoDB'nin tam
# yedegini alir (mongodump --archive --gzip) ve S3 uyumlu bir depoya
# yukler. Yerel kopyayi yukledikten sonra siler.
#
# UZAK SAKLAMA (retention): Eski yedeklerin silinmesi icin S3 tarafinda
# "lifecycle" kurali tanimlanmasi ONERILIR (orn: 30 gun sonra sil).
# Bu script S3'ten OBJE SILMEZ (kaza riski olmasin diye bilinctli).
# =====================================================================
set -euo pipefail

: "${MONGO_URL:?MONGO_URL gerekli (orn: mongodb://mongo:27017/hotel_pms)}"
: "${S3_BUCKET:?S3_BUCKET gerekli (orn: s3://otel-yedekleri)}"

BACKUP_TIME="${BACKUP_TIME:-03:00}"          # HH:MM, sunucu saat dilimi
S3_PREFIX="${S3_PREFIX:-syroce}"             # bucket icindeki klasor
TMP_DIR="${BACKUP_TMP_DIR:-/tmp/syroce-backup}"
RUN_ON_START="${BACKUP_RUN_ON_START:-false}" # konteyner ayaga kalkinca bir kez al

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] backup: $*"; }

do_backup() {
  local ts archive key
  ts="$(date -u +%Y%m%d-%H%M%S)"
  archive="${TMP_DIR}/syroce-${ts}.archive.gz"
  key="${S3_BUCKET}/${S3_PREFIX}/$(date -u +%Y/%m/%d)/syroce-${ts}.archive.gz"

  mkdir -p "${TMP_DIR}"
  log "mongodump basliyor -> ${archive}"
  mongodump --uri="${MONGO_URL}" --archive="${archive}" --gzip

  log "S3'e yukleniyor -> ${key}"
  # shellcheck disable=SC2086
  aws s3 cp "${archive}" "${key}" ${AWS_S3_EXTRA_ARGS:-}

  rm -f "${archive}"
  log "Yedek tamamlandi: ${key}"
}

if [ "${RUN_ON_START}" = "true" ]; then
  do_backup || log "ILK yedek BASARISIZ (rc=$?), zamanlanmis dongu yine de baslayacak."
fi

while true; do
  now_epoch="$(date +%s)"
  target_epoch="$(date -d "today ${BACKUP_TIME}" +%s 2>/dev/null || date -d "${BACKUP_TIME}" +%s)"
  if [ "${target_epoch}" -le "${now_epoch}" ]; then
    target_epoch="$(date -d "tomorrow ${BACKUP_TIME}" +%s)"
  fi
  sleep_secs="$(( target_epoch - now_epoch ))"
  log "Sonraki yedek ${BACKUP_TIME} icin ${sleep_secs}s bekleniyor."
  sleep "${sleep_secs}"
  do_backup || log "Yedek BASARISIZ (rc=$?), bir sonraki gune devam."
done

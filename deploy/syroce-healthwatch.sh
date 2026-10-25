#!/usr/bin/env bash
set -euo pipefail

readonly COMPOSE_DIR="${SYROCE_COMPOSE_DIR:-/opt/syroce-pms}"
readonly COMPOSE_FILE="${SYROCE_COMPOSE_FILE:-docker-compose.prod.yml}"
readonly HEALTH_URL="${SYROCE_HEALTH_URL:-https://pms.syroce.com/api/health/liveness}"

readonly -a SERVICES=(nginx backend frontend worker beat)
declare -Ar EXPECTED_REPLICAS=(
  [nginx]="${HEALTHWATCH_NGINX_REPLICAS:-1}"
  [backend]="${HEALTHWATCH_BACKEND_REPLICAS:-1}"
  [frontend]="${HEALTHWATCH_FRONTEND_REPLICAS:-1}"
  [worker]="${HEALTHWATCH_WORKER_REPLICAS:-1}"
  [beat]="${HEALTHWATCH_BEAT_REPLICAS:-1}"
)

compose() {
  # A failed Compose lookup is still surfaced below as a replica mismatch. Keep
  # deprecation/unset optional-variable warnings out of the five-minute systemd
  # journal so genuine health failures remain obvious.
  docker compose --project-directory "$COMPOSE_DIR" -f "$COMPOSE_DIR/$COMPOSE_FILE" "$@" 2>/dev/null
}

failures=()
for service in "${SERVICES[@]}"; do
  mapfile -t container_ids < <(compose ps --status running -q "$service")
  actual_count="${#container_ids[@]}"
  expected_count="${EXPECTED_REPLICAS[$service]}"

  if [[ "$actual_count" -ne "$expected_count" ]]; then
    failures+=("${service}:replicas=${actual_count}/${expected_count}")
    continue
  fi

  for container_id in "${container_ids[@]}"; do
    status="$(docker inspect --format '{{.State.Status}}/{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container_id" 2>/dev/null || true)"
    if [[ "$status" != "running/healthy" ]]; then
      failures+=("${service}:${status:-missing}")
    fi
  done
done

http_code="$(curl --connect-timeout 5 --max-time 10 --silent --show-error --output /dev/null --write-out '%{http_code}' "$HEALTH_URL" || true)"
if [[ "$http_code" != "200" ]]; then
  failures+=("external-health:${http_code:-unreachable}")
fi

# Existing five-minute host monitor also surfaces low disk capacity; it never
# deletes anything or weakens the image-retention rollback protections.
min_free_gib="${HEALTHWATCH_MIN_FREE_GIB:-10}"
if [[ ! "$min_free_gib" =~ ^[1-9][0-9]{0,3}$ ]] || ((min_free_gib > 1024)); then
  failures+=("disk-threshold:invalid")
else
  min_free_bytes=$((min_free_gib * 1024 * 1024 * 1024))
  docker_root="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || true)"
  if [[ "$docker_root" != /* || ! -d "$docker_root" ]]; then
    failures+=("docker-storage:unknown")
  else
    for disk_path in / "$docker_root" /var/lib/containerd; do
      [[ -d "$disk_path" ]] || continue
      available_bytes="$(df -PB1 "$disk_path" 2>/dev/null | awk 'NR == 2 {print $4}' || true)"
      if [[ ! "$available_bytes" =~ ^[0-9]+$ ]]; then
        failures+=("disk-free:unreadable")
      elif ((available_bytes < min_free_bytes)); then
        failures+=("disk-free:${disk_path}:${available_bytes}B<${min_free_gib}GiB")
      fi
    done
  fi
fi

if ((${#failures[@]})); then
  logger -t syroce-healthwatch -- "FAILED ${failures[*]}"
  printf 'FAILED %s\n' "${failures[*]}" >&2
  exit 1
fi

logger -t syroce-healthwatch -- "OK"
printf 'OK replicas=nginx:1,backend:%s,frontend:%s,worker:%s,beat:1 external-health=200\n' \
  "${EXPECTED_REPLICAS[backend]}" \
  "${EXPECTED_REPLICAS[frontend]}" \
  "${EXPECTED_REPLICAS[worker]}"

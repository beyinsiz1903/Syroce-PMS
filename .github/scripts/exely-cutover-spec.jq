def set_env($key; $value):
  .envs = ((.envs // [])
    | map(select(.key != $key))
    + [{"key": $key, "scope": "RUN_TIME", "type": "GENERAL", "value": $value}]);

.services |= map(
  if .name == "backend" then
    .image.tag = $sha
    | del(.image.digest)
    | set_env("ENABLE_EXELY_PRODUCTION"; $master)
    | set_env("DISABLE_EXELY_RESERVATION_SYNC"; $reservation_stop)
    | set_env("DISABLE_EXELY_ARI_WRITE"; $ari_stop)
    | set_env("NILVERA_ENABLED"; "false")
  elif .name == "frontend" then
    .image.tag = $sha | del(.image.digest)
  else . end
)
|
.workers |= map(
  if .name == "worker" or .name == "beat" then
    .image.tag = $sha
    | del(.image.digest)
    | set_env("ENABLE_EXELY_PRODUCTION"; $master)
    | set_env("DISABLE_EXELY_RESERVATION_SYNC"; $reservation_stop)
    | set_env("DISABLE_EXELY_ARI_WRITE"; $ari_stop)
    | set_env("NILVERA_ENABLED"; "false")
  else . end
)

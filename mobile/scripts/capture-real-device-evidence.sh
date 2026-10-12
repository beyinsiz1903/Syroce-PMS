#!/usr/bin/env bash

# Captures reviewable evidence from a signed iOS/Android build.  This never
# substitutes synthetic marketing assets for product evidence: every image is
# emitted by Maestro from the device currently selected by MAESTRO_DEVICE.
set -euo pipefail

artifact_dir="${MOBILE_EVIDENCE_DIR:-artifacts/mobile-device-evidence/$(date +%Y-%m-%d)}"
mkdir -p "$artifact_dir"

flows=(
  "frontdesk_today.yaml"
  "role_housekeeping.yaml"
  "role_manager.yaml"
  "guest_digital_key.yaml"
)

for flow in "${flows[@]}"; do
  name="${flow%.yaml}"
  echo "Capturing ${name} on ${MAESTRO_DEVICE:-default device}"
  maestro test \
    --format junit \
    --output "$artifact_dir/${name}.xml" \
    ".maestro/flows/${flow}"
done

echo "Device evidence written to $artifact_dir"

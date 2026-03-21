#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$ROOT_DIR/src"

python3 -m geo.cli --version
python3 -m geo.cli doctor --json >/tmp/geo_doctor.json
python3 -m geo.cli quick https://example.com --json >/tmp/geo_quick.json
python3 -m geo.cli audit https://example.com --json >/tmp/geo_audit.json
python3 -m geo.cli report-pdf /tmp/geo_audit.json --output /tmp/GEO-REPORT-smoke.pdf --json >/tmp/geo_pdf.json
python3 -m geo.cli compare /tmp/geo_audit.json /tmp/geo_audit.json >/tmp/geo_compare.txt
python3 -m geo.cli prospect new example.com --monthly-value 5000
python3 -m geo.cli prospect list --json >/tmp/geo_prospects.json
python3 -m geo.cli proposal example.com

echo "smoke ok"

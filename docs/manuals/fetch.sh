#!/usr/bin/env bash
# Download the reference PDFs this project's docs/ cite. None of these are
# redistributed in the repo — UR copyright. Re-run any time.

set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "${HERE}"

fetch() {
    local out="$1"; local url="$2"
    if [[ -f "${out}" ]]; then echo "✓ ${out} (cached)"; return; fi
    echo "↓ ${out}"
    curl -fsSL -o "${out}" "${url}"
}

# UR5e User Manual — PolyScope 5 / SW 5.21 (March 2025 build).
fetch "UR5e_User_Manual_SW5.21.pdf" \
    "https://s3-eu-west-1.amazonaws.com/ur-support-site/241080/710-965-00_UR5e_User_Manual_en_Global.pdf"

# Dashboard Server (port 29999) e-Series command reference, 2022.
fetch "DashboardServer_e-Series_2022.pdf" \
    "https://s3-eu-west-1.amazonaws.com/ur-support-site/42728/DashboardServer_e-Series_2022.pdf"

# URScript Manual (SW 5.11 is the last publicly-archived full script manual;
# SW 5.21 ships a "Script Directory" replacement whose URL is gated).
fetch "URScript_Manual_SW5.11.pdf" \
    "https://s3-eu-west-1.amazonaws.com/ur-support-site/115824/scriptManual_SW5.11.pdf"

echo
echo "Done. All files are gitignored — UR copyright, do not redistribute."

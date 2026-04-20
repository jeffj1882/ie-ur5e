#!/usr/bin/env bash
# Render every docs/*.md into a branded IE PDF under docs/pdf/.
# Usage: ./docs/_branding/build.sh [slug]     (omit slug to build all)

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DOCS="$(cd "$HERE/.." && pwd)"
OUT="$DOCS/pdf"
LOGO="$HERE/ie_logo.png"
HEADER="$HERE/header.tex"
TITLE="$HERE/titlepage.tex"

mkdir -p "$OUT"

ISSUED="$(date +'%Y-%m-%d')"
REVISION="$(cd "$DOCS/.." && git rev-parse --short HEAD 2>/dev/null || echo 'local')"

# Map: <slug>|<markdown-filename>|<doc-title>|<subtitle>
DOCS_LIST=(
  "00-overview|README.md|ie-ur5e Documentation|Index and repository overview"
  "01-connect-the-robot|01-connect-the-robot.md|Connecting the UR5e|First-time commissioning runbook"
  "02-dashboard-server|02-dashboard-server.md|Dashboard Server Reference|TCP :29999 command catalogue"
  "03-rtde|03-rtde.md|RTDE Reference|Real-Time Data Exchange subscription + watchdog"
  "04-safety|04-safety.md|Safety Reference|Stops, bits, and recovery procedures"
  "05-urscript-surface|05-urscript-surface.md|URScript Surface|Primitives used by ur\\_rtde"
)

render_one() {
  local slug="$1" md="$2" title="$3" subtitle="$4"
  local src="$DOCS/$md"
  local pdf="$OUT/${slug}.pdf"

  if [[ ! -f "$src" ]]; then
    echo "SKIP $slug — missing $src" >&2
    return
  fi

  echo "→ $pdf"
  pandoc "$src" \
    --from=gfm \
    --to=pdf \
    --pdf-engine=xelatex \
    --variable=documentclass:article \
    --variable=papersize:letter \
    --variable=colorlinks:true \
    --variable=geometry:margin=0.9in \
    --include-in-header="$HEADER" \
    --include-before-body="$TITLE" \
    --metadata=ielogo:"$LOGO" \
    --metadata=ietitle:"$title" \
    --metadata=iesubtitle:"$subtitle" \
    --metadata=ierevision:"$REVISION" \
    --metadata=ieissued:"$ISSUED" \
    --variable=header-includes:"\\newcommand{\\ielogo}{$LOGO}\\newcommand{\\ietitle}{$title}\\newcommand{\\iesubtitle}{$subtitle}\\newcommand{\\ierevision}{$REVISION}\\newcommand{\\ieissued}{$ISSUED}" \
    --highlight-style=tango \
    --output="$pdf"
}

if [[ $# -eq 1 ]]; then
  target="$1"
  for row in "${DOCS_LIST[@]}"; do
    IFS='|' read -r slug md title subtitle <<<"$row"
    if [[ "$slug" == "$target" ]]; then
      render_one "$slug" "$md" "$title" "$subtitle"
      exit 0
    fi
  done
  echo "unknown slug: $target" >&2
  exit 1
fi

for row in "${DOCS_LIST[@]}"; do
  IFS='|' read -r slug md title subtitle <<<"$row"
  render_one "$slug" "$md" "$title" "$subtitle"
done

echo
echo "Output: $OUT"
ls -la "$OUT"

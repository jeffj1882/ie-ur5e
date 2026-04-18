#!/usr/bin/env bash
# Build a Raspberry Pi 5 boot image preconfigured to run URSim on first boot.
#
# Downloads the official Ubuntu 24.04.3 Server arm64 raspi image, injects
# our cloud-init user-data + network-config + assets into its system-boot
# partition, and emits `ursim-pi.img` ready to flash with rpi-imager / dd.
#
# Mac-only (uses hdiutil). Re-entrant: skips the download + decompress if
# the cached artefacts are already on disk.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CACHE="${HERE}/.cache"
OUT="${HERE}/ursim-pi.img"

UBUNTU_VERSION="24.04.3"
IMG_NAME="ubuntu-${UBUNTU_VERSION}-preinstalled-server-arm64+raspi.img"
XZ_NAME="${IMG_NAME}.xz"
XZ_URL="https://cdimage.ubuntu.com/releases/${UBUNTU_VERSION}/release/${XZ_NAME}"
XZ_SHA256="9bb1799cee8965e6df0234c1c879dd35be1d87afe39b84951f278b6bd0433e56"

CACHED_XZ="${CACHE}/${XZ_NAME}"
CACHED_IMG="${CACHE}/${IMG_NAME}"

mkdir -p "${CACHE}"

# 1. Download + verify + decompress if needed.
if [[ ! -f "${CACHED_IMG}" ]]; then
    if [[ ! -f "${CACHED_XZ}" ]]; then
        echo "[1/5] downloading ${XZ_NAME} (~1 GB)…"
        curl -fL --progress-bar -o "${CACHED_XZ}" "${XZ_URL}"
    else
        echo "[1/5] using cached ${XZ_NAME}"
    fi
    echo "[2/5] verifying SHA256…"
    actual=$(shasum -a 256 "${CACHED_XZ}" | awk '{print $1}')
    if [[ "${actual}" != "${XZ_SHA256}" ]]; then
        echo "ERROR: SHA256 mismatch (expected ${XZ_SHA256}, got ${actual})"
        exit 1
    fi
    echo "[3/5] decompressing (requires ~7 GB disk)…"
    xz --decompress --keep --stdout "${CACHED_XZ}" > "${CACHED_IMG}"
else
    echo "[1-3/5] using cached decompressed image"
fi

# 2. Copy to OUT so we don't mutate the cache.
echo "[4/5] copying to ${OUT}"
cp -f "${CACHED_IMG}" "${OUT}"

# 3. Attach the image WITH automount so macOS mounts the FAT boot partition
#    at /Volumes/system-boot under our user — no sudo needed.
echo "[5/5] injecting cloud-init + URSim assets into system-boot partition…"
MAP=$(hdiutil attach "${OUT}")
# MAP looks like:
#   /dev/disk4        GUID_partition_scheme
#   /dev/disk4s1      Windows_FAT_32    /Volumes/system-boot
#   /dev/disk4s2      Linux
DEV=$(echo "${MAP}" | awk '/system-boot/ {print $1; exit}')
MNT=$(echo "${MAP}" | awk '/system-boot/ {print $3; exit}')
if [[ -z "${MNT}" || -z "${DEV}" ]]; then
    # Some systems give the FAT volume no label — fall back to the first FAT row.
    DEV=$(echo "${MAP}" | awk '/Windows_FAT_32|Apple_MSDOS|DOS_FAT_32/ {print $1; exit}')
    MNT=$(echo "${MAP}" | awk '/Windows_FAT_32|Apple_MSDOS|DOS_FAT_32/ {print $3; exit}')
fi
if [[ -z "${MNT}" ]]; then
    echo "ERROR: could not locate system-boot FAT32 partition inside ${OUT}"
    echo "hdiutil attach output was:"
    echo "${MAP}"
    hdiutil detach "${OUT}" 2>/dev/null || true
    exit 2
fi
PARENT_DEV="${DEV%s*}"
# shellcheck disable=SC2064
trap "hdiutil detach ${PARENT_DEV} 2>/dev/null || true" EXIT

echo "  FAT partition: ${DEV}"
echo "  mount:         ${MNT}"

# Render user-data with real SSH keys and a password hash. If any .pub key is
# present in ~/.ssh/, use all of them. Password defaults to "ursim".
PW_PLAINTEXT="${URSIM_PI_PASSWORD:-ursim}"
PW_HASH=$(openssl passwd -6 "${PW_PLAINTEXT}")

KEYS_BLOCK=""
shopt -s nullglob
for k in "${HOME}/.ssh/"*.pub; do
    KEYS_BLOCK+=$'      - '"$(tr -d '\n' < "$k")"$'\n'
done
shopt -u nullglob
if [[ -z "${KEYS_BLOCK}" ]]; then
    echo "WARNING: no ~/.ssh/*.pub keys found — image will rely on password login only."
    KEYS_BLOCK="      []"
fi

TMPUD=$(mktemp /tmp/ursim-user-data.XXXXXX)
python3 - "${HERE}/cloud-init/user-data" "${PW_HASH}" "${TMPUD}" <<'PY' "$(printf '%s' "${KEYS_BLOCK}")"
import sys, pathlib
template, pw_hash, out = sys.argv[1], sys.argv[2], sys.argv[3]
keys = sys.argv[4]
text = pathlib.Path(template).read_text()
text = text.replace("@PASSWORD_HASH@", pw_hash)
text = text.replace("@SSH_AUTHORIZED_KEYS@", keys.rstrip("\n"))
pathlib.Path(out).write_text(text)
PY

# COPYFILE_DISABLE keeps macOS from leaving `._foo` resource-fork sidecars on
# the FAT volume; cloud-init ignores them but they're noise on the boot partition.
COPYFILE_DISABLE=1 cp "${TMPUD}"                              "${MNT}/user-data"
COPYFILE_DISABLE=1 cp "${HERE}/cloud-init/network-config"     "${MNT}/network-config"
COPYFILE_DISABLE=1 cp "${HERE}/cloud-init/docker-compose.yml" "${MNT}/ursim-compose.yml"
# Clean any sidecars that were already there (e.g. from prior builds).
rm -f "${MNT}"/._* "${MNT}/.fseventsd"/._* 2>/dev/null || true
rm -f "${TMPUD}"
# meta-data already exists on the Ubuntu image, leave it alone.

sync
hdiutil detach "${PARENT_DEV}"
trap - EXIT

echo
echo "✔ Image built: ${OUT}"
echo "  size: $(du -h "${OUT}" | awk '{print $1}')"
echo
echo "Flash with rpi-imager (pick 'Use custom' → this .img) or:"
echo "  diskutil list                     # find the SD card disk identifier"
echo "  diskutil unmountDisk /dev/diskN"
echo "  sudo dd if=${OUT} of=/dev/rdiskN bs=4m status=progress"
echo
echo "Boot the Pi. First boot takes ~10 min (apt + docker pull + qemu setup)."
echo "Then SSH in: ssh ursim@ursim.local  (or the DHCP'd IP)"

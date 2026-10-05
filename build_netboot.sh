#!/usr/bin/env bash
# ==============================================================================
# iventoy-netloop: Netboot Kernel Builder
# Generates Standalone BIOS (i386-pc) and UEFI (x86_64-efi) GRUB netboot images
# with full HTTP 206 Loopback, GPT, Ext4, and Btrfs support.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${SCRIPT_DIR}/bin"
CONFIG_DIR="${SCRIPT_DIR}/config"

mkdir -p "${BIN_DIR}/i386-pc" "${BIN_DIR}/x86_64-efi"

MODULES="http net loopback part_gpt part_msdos ext2 btrfs fat ntfs iso9660 normal boot linux echo test ls date search tftp all_video gfxterm"

echo "[1/2] Building BIOS PXE image (i386-pc core.0)..."
grub-mkimage \
    -d /usr/lib/grub/i386-pc/ \
    -O i386-pc-pxe \
    -o "${BIN_DIR}/i386-pc/core.0" \
    -p '(pxe)/boot/grub' \
    pxe tftp http net loopback part_gpt part_msdos ext2 btrfs fat ntfs iso9660 normal boot linux echo test ls date search

echo "[2/2] Building UEFI Standalone image (x86_64-efi grubnet.efi)..."
grub-mkstandalone \
    -d /usr/lib/grub/x86_64-efi/ \
    -O x86_64-efi \
    --modules="${MODULES}" \
    -o "${BIN_DIR}/x86_64-efi/grubnet.efi" \
    "boot/grub/grub.cfg=${CONFIG_DIR}/grub_standalone.cfg"

echo "=== Build Complete ==="
ls -lh "${BIN_DIR}/i386-pc/core.0" "${BIN_DIR}/x86_64-efi/grubnet.efi"

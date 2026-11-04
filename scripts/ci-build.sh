#!/usr/bin/env bash
# Build driver for the PD2048 (vivo S9e / MT6875) kernel port.
# Runs inside GitHub Actions, but is plain bash so it also works on any Linux box.
#
#   ./scripts/ci-build.sh apply   # copy overlay/ into the kernel tree, apply patches/
#   ./scripts/ci-build.sh build   # configure + compile
#
# Env knobs: KERNEL_DIR, CLANG_DIR, CROSS_PREFIX, DEFCONFIG, TARGET, JOBS, KCFLAGS
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KERNEL_DIR="${KERNEL_DIR:-$ROOT/kernel}"
CLANG_DIR="${CLANG_DIR:-$ROOT/toolchains/clang}"
CROSS_PREFIX="${CROSS_PREFIX:-aarch64-linux-gnu-}"
DEFCONFIG="${DEFCONFIG:-bomb_user_defconfig}"
TARGET="${TARGET:-Image.gz}"
JOBS="${JOBS:-8}"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
die() { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

apply() {
    [ -d "$KERNEL_DIR" ] || die "kernel tree missing: $KERNEL_DIR"

    if [ -d "$ROOT/overlay" ]; then
        log "copying overlay/ into kernel tree"
        cp -a "$ROOT/overlay/." "$KERNEL_DIR"/
    fi

    shopt -s nullglob
    local patches=("$ROOT"/patches/*.patch)
    if [ ${#patches[@]} -gt 0 ]; then
        for p in "${patches[@]}"; do
            log "applying $(basename "$p")"
            git -C "$KERNEL_DIR" apply --whitespace=nowarn -p1 "$p" \
                || die "patch failed: $p"
        done
    else
        log "no patches/ entries"
    fi
    shopt -u nullglob
}

build() {
    [ -d "$KERNEL_DIR" ] || die "kernel tree missing: $KERNEL_DIR"
    [ -x "$CLANG_DIR/bin/clang" ] || die "clang missing: $CLANG_DIR/bin/clang"
    [ -x "$(command -v "${CROSS_PREFIX}as")" ] || die "binutils missing: ${CROSS_PREFIX}as"

    export PATH="$CLANG_DIR/bin:$PATH"
    export ARCH=arm64
    export SUBARCH=arm64
    export KBUILD_BUILD_USER=pd2048
    export KBUILD_BUILD_HOST=gha

    # clang builds its external-assembler path from --prefix; point that at a
    # directory whose `as` is the cross assembler (see the Makefile patch).
    export CROSS_BIN_DIR="$ROOT/toolchains/crossbin"
    mkdir -p "$CROSS_BIN_DIR"
    ln -sf "$(command -v "${CROSS_PREFIX}as")" "$CROSS_BIN_DIR/as"
    ln -sf "$(command -v "${CROSS_PREFIX}objcopy")" "$CROSS_BIN_DIR/objcopy"
    ln -sf "$(command -v "${CROSS_PREFIX}strip")" "$CROSS_BIN_DIR/strip"

    # clang compiles C; GNU binutils (aarch64-linux-gnu) provides as/objcopy;
    # lld links. This avoids the fragile AOSP gcc-4.9 prebuilt package.
    local make_args=(
        O=out
        ARCH=arm64
        CC=clang
        LD=ld.lld
        CLANG_TRIPLE=aarch64-linux-gnu
        CROSS_COMPILE="$CROSS_PREFIX"
    )

    cd "$KERNEL_DIR"
    log "kernel $(make kernelversion 2>/dev/null || echo unknown), defconfig=$DEFCONFIG"
    log "configure"
    make "${make_args[@]}" "$DEFCONFIG"

    log "compile with -j$JOBS"
    set +e
    make -j"$JOBS" "${make_args[@]}" V=1 ${KCFLAGS:+KCFLAGS="$KCFLAGS"} "$TARGET" 2>&1 | tee error.log
    local rc=${PIPESTATUS[0]}
    set -e
    if [ "$rc" -ne 0 ]; then
        log "BUILD FAILED (rc=$rc); last errors:"
        grep -E "error:|Error [0-9]" error.log | tail -50 || true
        exit "$rc"
    fi

    log "output:"
    ls -lh "out/arch/arm64/boot/$TARGET"
    file "out/arch/arm64/boot/$TARGET" || true
}

case "${1:-}" in
    apply) apply ;;
    build) build ;;
    *) die "usage: $0 {apply|build}" ;;
esac

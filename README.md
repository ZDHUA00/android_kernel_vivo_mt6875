# PD2048 kernel port (vivo S9e / MT6875 / 4.14.186)

LineageOS bring-up for the vivo S9e (PD2048). The stock vivo kernel is **not**
used: the kernel is built from the Xiaomi `bomb` (Redmi 10X Pro, MT6875) 4.14.186
source and gets the PD2048 board description appended as a DTB.

## Why this base

* `xszx/kernel_xiaomi_bomb` (`cezanne-r-oss`) is the only public MT6875 4.14
  kernel which matches the stock PD2048 kernel version (`4.14.186+`, clang
  11.0.1, LLD 11).
* PD2048 board files (227 KB DTS, 643 compatibles) were extracted from the
  6.13.30 `boot.img` DTB; `dtbo.img` adds 144 KB of overlay.
* The stock DTB is reused as a binary blob at first (`Image.gz` + `boot_61330.dtb`),
  so the first milestone is a *booting* custom kernel, not a full DTS rewrite.

## Pipeline

```
GitHub Actions
  clone bomb source (cezanne-r-oss)
  download clang-r416183b + aarch64-linux-android-4.9
  apply overlay/ and patches/
  make O=out bomb_user_defconfig
  make O=out Image.gz
  -> artifact: Image.gz, .config, System.map, error.log
```

Locally (Windows) `tools/splice_boot.py` puts `Image.gz` + the stock PD2048 DTB
into the stock `boot.img` so it can be flashed with the usual MTK flashing path.

## Repository layout

| path | purpose |
|---|---|
| `scripts/ci-build.sh` | apply + build driver (CI and local Linux) |
| `overlay/` | files copied verbatim over the kernel tree |
| `patches/` | `git apply` patch series, applied in name order |
| `tools/splice_boot.py` | rebuild `boot.img` from stock boot + new kernel |
| `docs/` | notes, driver inventory, offsets |

## Status

- [x] source + toolchain pinned, CI pipeline written
- [x] first green build (`bomb_user_defconfig`, run 41913446650)
- [ ] boot PD2048 with stock DTB (adb expected, no display yet)
- [ ] port vivo private drivers (charge/battery/touch/typec)
- [ ] panel driver `s6e3fc3` (90/60 Hz)
- [ ] LineageOS 20 GSI on the system logical partition

### Toolchain notes (hard-won)

The AOSP gcc-4.9 prebuilt tarball on the runner has no `aarch64-linux-android-gcc`
driver binary, and clang's `--prefix` resolves the assembler to the host
`/usr/bin/as` (which then rejects `-EL`). The working combination is:

* Ubuntu `binutils-aarch64-linux-gnu` for `as`/`objcopy`/`strip`
* `patches/0001-clang-cross-toolchain-dir.patch` pointing `GCC_TOOLCHAIN_DIR`
  at `$CROSS_BIN_DIR` (a shim dir whose `as` is the cross assembler),
  exported from `scripts/ci-build.sh`
* clang-r416183b for C, `ld.lld` for linking, `CLANG_TRIPLE=aarch64-linux-gnu`

### Flashing is gated by LK

`fastboot flash/erase` on this device always fails with `unknown reason`; expdb
shows `[FASTBOOT]fb_get_verify_unlock_state verify state is 1`. That RAM global is
initialised to 1 in `.data` and is only cleared by an RSA-signed `verify:unlock`,
so an unlocked seccfg is not enough. Until that gate is bypassed (LK code
execution), the boot partition cannot be replaced — the kernel artifacts here are
built but cannot be flashed yet.

The 13 vivo-only compatibles and the 3 panel compatibles are listed in
`docs/driver-gaps.md`.

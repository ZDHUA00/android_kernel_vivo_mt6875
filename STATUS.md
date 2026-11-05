# Status / handoff

_Last updated: 2026-11-05_

## What works

| item | evidence |
|---|---|
| Kernel builds from bomb (MT6875, 4.14.186) source | `bomb_user_defconfig`: runs 41913446650 / 41917885106 / #29 `success`; stock `pd2048_defconfig`: run #31 `success` after the fixes in `docs/driver-gaps.md` |
| Artifact | `Image.gz` 13,343,894 B, `Image` 35,717,136 B, version string `4.14.186+ (pd2048@gha)` |
| Boot image assembled with stock DTB + ramdisk | `boot_pd2048_test.img`, 100,663,296 B, header v2, DTBO `d7b7ab1e`, DTB 160,015 B |
| Toolchain recipe | see README "Toolchain notes"; `patches/0001-clang-cross-toolchain-dir.patch` |
| Stock-config gap list | `docs/driver-gaps.md`, 5 compiler-verified items, 2 fixed |
| **Kernel can be test-booted without flashing boot** | recovery.img carries the *same* kernel as boot.img — see `docs/recovery-testbed.md` |

## What is blocked: fastboot flashing

Flashing **any** partition over fastboot fails:

```
fastboot flash boot  -> FAILED (remote: 'unknown reason')
fastboot flash misc  -> FAILED (remote: 'unknown reason')
fastboot erase misc  -> FAILED (remote: 'unknown reason')
```

expdb (sdc4) shows the reason:

```
[FASTBOOT]fb_get_verify_unlock_state verify state is 1
```

Disassembly of `fb_do_verify` (0x30fcc): the global at `.data` payload 0xC6CB4
(runtime VA `0x4C4C6AB4`) is initialised to **1** and is only cleared by a
successful RSA-2048 signed `verify:unlock`. An unlocked seccfg (`lock_state=3`,
`getvar unlocked:yes`, boot state orange) does not affect it.

### ultraflash does NOT bypass the gate (verified by disassembly)

`oem ultraflash_en 1` sets a flag; the flash handler then calls `0x3795c`, which is
a **partition-name whitelist** (17 names, 0x20 bytes each). It returns 1 when the
name is whitelisted, and the handler then branches **back to the normal path**
(0x37aca → 0x37620 → 0x3734c → `fb_get_verify_unlock_state`). Non-whitelisted names
fail with a message. So enabling ultraflash cannot skip the verify check — no point
testing it on hardware.

### The 62-byte BOF clears the gate but kills LK (measured 2026-11-05)

The `oem getinfo` overflow does write `[0x4C4C6AB4] = 0`, and returns to the
fastboot loop — but LK dies immediately afterwards:

* gadget `0x2f5b8` is `str r2,[r4,#0x64] ; lsls r7,r0,#0 ; movs r0,#0 ; bx lr`.
  `oem getinfo` always returns 0 (`0x31134 movs r0,#0`), so **r7 = 0**.
* `bx lr` → `0x2d7ba` → `b 0x2d778`: `ldr r4,[r5]` (r4 = 1, set by dispatch)
  → `bl 0x70a8c` → `ldr r3,[r7,#0xc]` with `r7 = 0` → fault. Keeping r5 intact
  is **not** sufficient.
* Unicorn rejects every repair (`lkfuzz/emu_return.py`, `emu_return_r7ok.py`):
  one 4-byte store cannot nop both `ldr r3,[r7,…]` instructions, and all 7
  store-to-`[r4]` gadgets in the image clobber r7. No 8-byte write exists.
* Consequence: **clearing the gate and flashing in the same LK session is not
  possible with this primitive.** The way forward is a different bug (a handler
  whose return path does not consume r7) or a write-and-die primitive that
  performs the persistent write itself (e.g. UFS WP clear — the LK image
  contains `ufs_clr_write_protect` / `rpmb_ufs_clr_wp` symbols).

## Known-good facts for the exploit work

* the dispatcher calls the command handler with `blx r3` at **0x2d7b8**, so at the
  overflowed handler's return **lr = 0x2d7ba**, which is `b 0x2d778` — the fastboot
  loop continuation. The handler's epilogue restores sp, but the dispatcher then
  consumes **r7**, which the write gadget zeroes.
* hijack stack pointer from expdb panic dumps: `S = 0x4C79A410` (three dumps, identical)
* payload window: `0x4C79A3E0 .. 0x4C79A40F`
* dispatcher r5 must be restored to `0x4C501CC4`
* gadget (bytes inside a data table, but they decode as instructions):
  `0x2f5b8: 62 66 07 00 00 20 70 47` =
  `str r2,[r4,#0x64] ; lsls r7,r0,#0 ; movs r0,#0 ; bx lr`, VA `0x4C42F3B8`
* payload (62 B): `"oem getinfo A "` + 36×`A` + `LE32(0x4C4C6A50)` +
  `LE32(0x4C501CC4)` + `LE32(0x4C42F3B9)`, i.e. r4 = verify_global-0x64,
  r5 = dispatcher state, lr = gadget|thumb. All bytes are free of NUL/space.
* driver script: `lkfuzz/exploit_clear_verify.py` (`--dump` verified, `--fire` sends)
* **gadget validated in Unicorn** (`lkfuzz/emu_gadget.py`): starting with
  `r4=0x4C4C6A50, r2=0, lr=0x4C42D7BA, r5=0x4C501CC4, sp=0x4C79A410`, execution at
  `0x4C42F3B8` sets `[0x4C4C6AB4]` from 1 to 0 and branches via `bx lr`.

## Recovery is a disposable kernel test bed

Measured on the 6.13.30 package:

```
boot.img      kernel 14,168,565 B  md5 2f17f1623ddd2462ac1298d39e3520ba
recovery.img  kernel 14,168,565 B  md5 2f17f1623ddd2462ac1298d39e3520ba   # identical
```

* recovery is 96 MiB at LBA 0x8 (32 KiB) — **outside** the UFS WP range
  (WP starts at sector 0x32800 = 808 MiB).
* it is writable from Android root (`dd`) and restored to stock on the next normal
  boot, so a broken kernel costs exactly one boot.
* procedure: splice `Image.gz` into a recovery image, `dd` to
  `/dev/block/by-name/recovery`, write `boot-recovery` into `misc`, reboot, check
  `/proc/version` and `dmesg`. Full guide: `docs/recovery-testbed.md`;
  script: `tools/test_kernel_via_recovery.py`.
* caveat: not a daily-driver boot path. The panel driver is still missing, so
  expect a dark screen and adb-only access.

## Next actions (in order)

1. Recovery test bed: boot `Image.gz` via recovery, confirm `/proc/version`, and
   collect `dmesg` probe failures. This is the feedback loop for driver work.
2. Merge the stock PD2048 DTS (extracted from boot.img, DTB at file offset
   15,794,240) into the bomb tree, then fill the gaps listed in
   `docs/driver-gaps.md` (13 vivo-private compatibles, 3 panel, 6 peripherals).
3. Independent of the gate: GSI on the `super` partition (fastbootd can write
   logical partitions) — keeps the stock kernel.
4. LK gate (long-term): a handler with a different return path, or a
   write-and-die primitive (UFS WP clear) that persists across reboot.

## Rollback

Stock boot image: `D:\Zcode\ghostlock\fw\boot_61330.img` (100,663,296 B, md5 in
the 6.13.30 package). Recovery needs no rollback: it is restored automatically on
the next normal boot.

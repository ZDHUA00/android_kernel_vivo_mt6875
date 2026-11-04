# Status / handoff

_Last updated: 2026-11-05_

## What works

| item | evidence |
|---|---|
| Kernel builds from bomb (MT6875, 4.14.186) source | Actions runs 41913446650 and 41917885106, `success` |
| Artifact | `Image.gz` 13,343,894 B, `Image` 35,717,136 B, version string `4.14.186+ (pd2048@gha)` |
| Boot image assembled with stock DTB + ramdisk | `boot_pd2048_test.img`, 100,663,296 B, header v2, DTBO `d7b7ab1e`, DTB 160,015 B |
| Toolchain recipe | see README "Toolchain notes"; `patches/0001-clang-cross-toolchain-dir.patch` |
| Stock-config gap list | `docs/driver-gaps.md`, 5 compiler-verified items, 2 fixed |

## What is blocked

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

## Known-good facts for the exploit work

* the dispatcher calls the command handler with `blx r3` at **0x2d7b8**, so at the
  overflowed handler's return **lr = 0x2d7ba**, which is `b 0x2d778` — i.e. the
  fastboot loop continuation. The handler's epilogue already restored sp, and the
  dispatcher reloads r4/r7 from `[r5]`; **only r5 must survive**. No stack pivot
  is needed.
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
* open question: whether r2 is 0 at the hijack (the panic dumps say 0). If it is
  not, the store writes a non-zero value, LK survives, and another gadget can be
  tried.

## Next actions (in order)

1. **phone must be power-cycled** (hold power 15-20 s) — it is stuck in LK's
   download receive loop after an `oem ultraflash:boot` attempt.
2. `python -I lkfuzz/exploit_clear_verify.py --fire` (sends the BOF, checks LK is
   still alive), then **in the same LK session**:
   `fastboot flash boot boot_pd2048_test.img`.
3. if r2 was not zero: try a gadget storing r1, or find another write primitive.
4. independent of the gate: GSI on the `super` partition (fastbootd can write
   logical partitions) — keeps the stock kernel.

## Rollback

Stock boot image: `D:\Zcode\ghostlock\fw\boot_61330.img` (100,663,296 B, md5 in
the 6.13.30 package). Flashing it back restores the stock kernel.

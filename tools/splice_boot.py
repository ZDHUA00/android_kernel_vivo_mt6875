"""Rebuild the PD2048 boot.img with a new kernel, keeping stock ramdisk + DTBO.

MTK boot.img (Android header v2) layout used by PD2048:

    [header, page 2048]
    [kernel  Image.gz        ]  padded to page
    [ramdisk                ]  padded to page
    [dtbo container (64 B hdr + DTBs)]

The DTBO container after the ramdisk is what the bootloader hands to the
kernel; it is copied verbatim so the board description stays stock.

Usage:
  python -I splice_boot.py --stock boot_61330.img --kernel Image.gz --out boot_pd2048.img
  python -I splice_boot.py --stock ... --kernel Image.gz --dtb boot_61330.dtb --out ...
"""
import argparse
import struct
import sys


def align(n, page):
    return (n + page - 1) // page * page


def parse(blob):
    if blob[:8] != b"ANDROID!":
        raise SystemExit("not an ANDROID! boot image")
    kernel_size = struct.unpack_from("<I", blob, 8)[0]
    ramdisk_size = struct.unpack_from("<I", blob, 16)[0]
    second_size = struct.unpack_from("<I", blob, 24)[0]
    page = struct.unpack_from("<I", blob, 36)[0]
    k_off = page
    r_off = k_off + align(kernel_size, page)
    s_off = r_off + align(ramdisk_size, page)
    tail_off = s_off + align(second_size, page)
    return dict(kernel_size=kernel_size, ramdisk_size=ramdisk_size,
                second_size=second_size, page=page,
                kernel=blob[k_off:k_off + kernel_size],
                ramdisk=blob[r_off:r_off + ramdisk_size],
                tail=blob[tail_off:])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock", required=True)
    ap.add_argument("--kernel", required=True, help="Image.gz from the kernel build")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dtb", help="optional: replace the DTB inside the DTBO container")
    args = ap.parse_args()

    with open(args.stock, "rb") as f:
        stock_blob = f.read()
    with open(args.kernel, "rb") as f:
        kernel = f.read()

    if kernel[:2] != b"\x1f\x8b":
        print("warning: kernel is not gzip; boot header v2 expects Image.gz",
              file=sys.stderr)

    info = parse(stock_blob)
    page = info["page"]
    header = bytearray(stock_blob[:page])
    struct.pack_into("<I", header, 8, len(kernel))

    tail = info["tail"]
    if args.dtb:
        with open(args.dtb, "rb") as f:
            dtb = f.read()
        magic, total, hdr_size, entry_size, count, entries_off = \
            struct.unpack_from(">6I", tail, 0)
        if magic != 0xD7B7AB1E:
            raise SystemExit(f"unexpected DTBO magic 0x{magic:08x}")
        if count != 1:
            raise SystemExit(f"expected 1 DTBO entry, got {count}")
        new_total = hdr_size + entry_size + len(dtb)
        new_tail = bytearray(tail[:hdr_size])
        struct.pack_into(">I", new_tail, 4, new_total)
        new_tail += tail[hdr_size:hdr_size + entry_size]
        struct.pack_into(">I", new_tail, hdr_size + 0, len(dtb))
        struct.pack_into(">I", new_tail, hdr_size + 4, hdr_size + entry_size)
        new_tail += dtb
        tail = bytes(new_tail)

    out = bytearray()
    out += header
    out += kernel
    out += b"\0" * (align(len(kernel), page) - len(kernel))
    out += info["ramdisk"]
    out += b"\0" * (align(len(info["ramdisk"]), page) - len(info["ramdisk"]))
    out += tail

    # keep the stock image size so the flash tool sees the same partition payload
    if len(out) < len(stock_blob):
        out += b"\0" * (len(stock_blob) - len(out))
    elif len(out) > len(stock_blob):
        raise SystemExit(f"new image ({len(out):,}) exceeds stock size "
                         f"({len(stock_blob):,})")

    with open(args.out, "wb") as f:
        f.write(out)

    print(f"kernel  {len(kernel):,} bytes (stock {info['kernel_size']:,})")
    print(f"ramdisk {len(info['ramdisk']):,} bytes (kept)")
    print(f"dtbo    {len(tail):,} bytes (kept)")
    print(f"wrote   {args.out}  {len(out):,} bytes")


if __name__ == "__main__":
    main()

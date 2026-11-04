"""Dump an Android/MTK boot image header (v0-v2) and section offsets."""
import struct
import sys


def u32(b, off):
    return struct.unpack_from("<I", b, off)[0]


def main(path):
    with open(path, "rb") as f:
        head = f.read(4096)
    magic = head[:8]
    print("file:", path)
    print("magic:", magic)
    if magic != b"ANDROID!":
        print("not an ANDROID! boot image")
        return 1
    kernel_size, kernel_addr, ramdisk_size, ramdisk_addr = struct.unpack_from("<4I", head, 8)
    second_size, second_addr, tags_addr, page_size, header_version, os_version = \
        struct.unpack_from("<6I", head, 24)
    name = head[48:64].rstrip(b"\0")
    cmdline = head[64:576].rstrip(b"\0")
    print(f"kernel_size   {kernel_size:,} (0x{kernel_size:x})  addr 0x{kernel_addr:x}")
    print(f"ramdisk_size  {ramdisk_size:,} (0x{ramdisk_size:x})  addr 0x{ramdisk_addr:x}")
    print(f"second_size   {second_size:,}  addr 0x{second_addr:x}")
    print(f"tags_addr     0x{tags_addr:x}")
    print(f"page_size     {page_size}")
    print(f"header_version {header_version}")
    print(f"os_version    0x{os_version:08x}")
    print(f"name          {name!r}")
    print(f"cmdline       {cmdline!r}")
    pages = lambda n: (n + page_size - 1) // page_size * page_size
    k_off = page_size
    r_off = k_off + pages(kernel_size)
    s_off = r_off + pages(ramdisk_size)
    print(f"kernel  @ {k_off:,} .. {k_off + kernel_size:,}")
    print(f"ramdisk @ {r_off:,} .. {r_off + ramdisk_size:,}")
    if second_size:
        print(f"second  @ {s_off:,} .. {s_off + second_size:,}")
    tail = s_off + pages(second_size)
    with open(path, "rb") as f:
        f.seek(tail)
        chunk = f.read(4096)
    print(f"tail    @ {tail:,} first bytes: {chunk[:16].hex()}")
    import re
    with open(path, "rb") as f:
        data = f.read()
    for m in re.finditer(b"\xd0\x0d\xfe\xed", data):
        off = m.start()
        total = struct.unpack_from(">I", data, off + 4)[0]
        print(f"DTB magic @ {off:,} totalsize {total:,} end {off + total:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))

#!/usr/bin/env python3
"""
extract_lut31.py — 提取并分析 aiqb id31 (GAMMA-LUT / 0-255 tone-map LUT)。

Intel IPU6 aiqb 用 id31 记录存放 0-255 域的音调映射/LUT 曲线。本脚本:
  1. 解析记录链找到 id31
  2. dump 其字节并尝试按 256 条目 LUT 解码 (每通道? 每亮度 1 输出?)
  3. 打印曲线结构供移植到 soft ISP 滚降/gamma

用法: python3 extract_lut31.py <file.aiqb>
"""
import struct, sys

FIRST = 0x50

def parse_records(data):
    recs = []
    o = FIRST
    n = len(data)
    while o + 8 <= n:
        size = struct.unpack_from("<I", data, o)[0]
        fmt = data[o + 4]
        key = data[o + 5]
        name = struct.unpack_from("<H", data, o + 6)[0]
        recs.append((o, size, fmt, key, name))
        if size < 8:
            break
        o += size
    return recs

def f32(data, off):
    return struct.unpack_from("<f", data, off)[0]

def hexdump(data, off, n, cols=16):
    for i in range(0, n, cols):
        row = data[off+i:off+i+cols]
        h = " ".join("%02x" % b for b in row)
        a = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        print("  %04x  %-*s  %s" % (i, cols*3, h, a))

def main():
    fn = sys.argv[1]
    data = open(fn, "rb").read()
    recs = parse_records(data)
    target = int(sys.argv[2], 0) if len(sys.argv) > 2 else 31
    print(f"File: {fn} ({len(data)} bytes), decoding id{target}")
    for off, size, fmt, key, name in recs:
        if name == target:
            body = off + 8
            print(f"id{target} @0x{off:x} size={size} (0x{size:x}) fmt={fmt} key={key}, body@0x{body:x}")
            bodydata = data[body:off+size]
            print("\n=== first 80 bytes of body ===")
            hexdump(data, body, min(80, size))
            # try parsing as 256-entry LUT
            print("\n=== try: 256 entry LUT (float32) ===")
            nbyte = size - 8
            if nbyte % 256 == 0 and size > 256:
                stride = nbyte // 256
                print(f"  body size {nbyte} = 256 * {stride}")
            # just dump 0..255 float values reading from body
            nf = nbyte // 4
            print(f"  body has {nf} float32 values")
            vals = struct.unpack_from("<%df" % nf, data, body)
            print("  first 40:", ["%.4f" % v for v in vals[:40]])
            print("  last 40 :", ["%.4f" % v for v in vals[-40:]])
            return
    print(f"id{target} not found")

if __name__ == "__main__":
    main()

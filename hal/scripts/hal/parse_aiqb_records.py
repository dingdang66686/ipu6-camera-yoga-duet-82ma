#!/usr/bin/env python3
"""
parse_aiqb_records.py — 解析 Intel IPU6 AIQB (ia_mkn/CPFF) 记录链。

参考: https://jetm.github.io/blog/posts/ipu6-aiqb-calibration/
AIQB 是 flat 的 tagged record 链，从 0x50 起，每条 8 字节头:
    [u32 size][u8 fmt][u8 key][u16 name_id],  next = cur + size

用法:
    python3 parse_aiqb_records.py gc5035_CJAK519_TGL.aiqb [--full]
默认打印每记录概要；--full 额外 dump 关键记录内部结构。
"""
import struct, sys, os

FIRST = 0x50

# name_id 语义 (对照 ov2740 博客 + 实测)
NAME = {
    1: "GENERAL_HDR", 2: "GENERAL_DATA", 3: "AWB/CHROMA",
    7: "SENSITIVITY", 9: "?", 13: "ISO/EXPOSURE-REL",
    15: "ISO-COLOR/GAIN", 17: "BAYER/SINGLE-VAL", 19: "?",
    20: "?", 22: "AWB", 25: "ADV_COLOR_MATRICES(CCM)",
    26: "BLACK_LEVEL", 28: "LSC/VIGNETTING", 29: "GRID/GAMMA",
    31: "GAMMA-LUT", 34: "STRIP", 0: "FOOTER",
}


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


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    fn = sys.argv[1]
    full = "--full" in sys.argv
    data = open(fn, "rb").read()
    print(f"File: {fn} ({len(data)} bytes)")
    recs = parse_records(data)
    print("\n=== Record chain ===")
    for off, size, fmt, key, name in recs:
        label = NAME.get(name, f"id{name}?")
        print(f"  @0x{off:06x}  name_id={name:<3} {label:<20} size={size:>7} (0x{size:x}) fmt={fmt} key={key}")

    # ---- 关键记录解码 ----
    d = data
    print("\n=== Key records ===")

    def rec_by_name(nm):
        for off, size, fmt, key, name in recs:
            if name == nm:
                return off, size
        return None

    # id2 GENERAL_DATA
    r = rec_by_name(2)
    if r and full:
        off, size = r
        w, h = struct.unpack_from("<HH", d, off + 8)
        bit = d[off + 12]
        print(f"id2 GENERAL_DATA: {w}x{h}, {bit}-bit, bayer_order={d[off+13] if off+13<len(d) else '?'}")

    # id7 sensibility
    r = rec_by_name(7)
    if r and full:
        off, size = r
        iso = struct.unpack_from("<H", d, off + 8)[0]
        print(f"id7 SENSITIVITY: Base ISO = {iso}")

    # id25 CCM
    r = rec_by_name(25)
    if r:
        off, size = r
        body = off + 8
        nls = struct.unpack_from("<H", d, body)[0]
        ns = struct.unpack_from("<H", d, body + 2)[0]
        print(f"\nid25 ADV_COLOR_MATRICES: num_light_srcs={nls}, num_sectors={ns}")
        # each source: src_type(u32) rpg f bpg f cix f ciy f cct u32 + traditional[9] + advanced[ns][9]
        # 注意: hue_of_sectors[ns] u32 在 header 与 data 之间
        p = body + 4 + ns * 4
        for i in range(nls):
            src_type = struct.unpack_from("<I", d, p)[0]
            rpg = f32(d, p + 4)
            bpg = f32(d, p + 8)
            cx = f32(d, p + 12)
            cy = f32(d, p + 16)
            cct = struct.unpack_from("<I", d, p + 20)[0]
            tr = struct.unpack_from("<9f", d, p + 24)
            rs = [sum(tr[0:3]), sum(tr[3:6]), sum(tr[6:9])]
            print(f"   src{i}: type={src_type} CCT={cct}K R/G={rpg:.4f} B/G={bpg:.4f} cx={cx:.4f} cy={cy:.4f}")
            if full:
                print(f"     CCM={['% .4f' % x for x in tr]}  rowsums={['%.3f' % x for x in rs]}")
            p += 24 + 36 + ns * 36

    # id26 black level
    r = rec_by_name(26)
    if r and full:
        off, size = r
        body = off + 8
        vals = struct.unpack_from("<%df" % (size // 4), d, off)
        print(f"\nid26 BLACK_LEVEL (raw floats from record start):")
        print("  ", [(i, "%.4g" % v) for i, v in enumerate(vals)])

    if not full:
        print("\n(用 --full 查看关键记录内部结构)")


if __name__ == "__main__":
    main()

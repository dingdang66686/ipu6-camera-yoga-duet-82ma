#!/usr/bin/env python3
"""
解析 Intel IPU6 aiqb (CPFF container) 结构，并扫描其中的 CCM/色彩矩阵候选。

aiqb 头部结构：
  offset 0: 'CPFF' + uint32 size
  offset 8..: 分块表: 每项 = 4字节tag + uint32 size
    LCMC, DFLT, AIQB ...
实际 Layout（从 dump 观察）:
  0x00  CPFF  <total size>
  0x08  <hash/checksum 8B?>
  0x10  00000000
  0x14  ...
  0x18  'LCMC'  <size>
  0x20  01000000 00000000
  0x2c  'DFLT'  <size>
  0x34  00000000 00000000
  0x38  'AIQB'  <size>
  0x40  00000000 00000000
  0x48  00000000 00000000
  0x50  元数据: <version blocks> ... IQStudio ... LibIQ ... ATE ... time

扫描策略：
  - 找 CCM: 连续 9 个 float32，对角线(第0,4,8个)在 0.5~3.0 且明显区别于：
      * AWB gains(R,G,B 3值 ~0.5~4)
      * gamma LUT
  - 找 "CCM" 风格：行主序 [c00 c01 c02 c10 c11 c12 c20 c21 c22]
"""
import struct, sys, re

def u32(b, off): return struct.unpack_from('<I', b, off)[0]
def f32(b, off): return struct.unpack_from('<f', b, off)[0]

def parse(path):
    data = open(path, 'rb').read()
    print(f"== {path} ({len(data)} bytes) ==")
    magic = data[0:4]
    print("magic:", magic)
    if magic != b'CPFF':
        print("  [警告] 非 CPFF 容器"); return data

    # 顶部容器大小
    top_size = u32(data, 4)
    print(f"container size field = 0x{top_size:x} ({top_size})")

    # 在头部找所有 4 字节 tag + size
    print("\n--- 头部块表 ---")
    off = 0
    for m in re.finditer(rb'[A-Z][A-Z0-9]{2,3}', data[0:0x80]):
        tag = m.group().decode()
        to = m.start()
        if to + 8 <= len(data):
            sz = u32(data, to+4)
            print(f"  0x{to:04x}  {tag}  size=0x{sz:x} ({sz})")
    return data

def scan_ccm(data, tag_end=0x400, show=True):
    """在数据区找 9-float CCM 候选: 对角线[0,4,8]∈[0.5,3]非单位对角, 非对角小。"""
    cands = []
    n = len(data)
    # 大步扫描太慢，用 find 定位 float 密集区
    for off in range(0, n-36, 4):
        try:
            c = [f32(data, off+i*4) for i in range(9)]
        except struct.error:
            break
        # 过滤合法的浮点
        if not all(0.0 < abs(v) < 100 for v in c):
            continue
        diag = [c[0], c[4], c[8]]
        offd = [c[1], c[2], c[3], c[5], c[6], c[7]]
        # 对角线主导、值在 0.3~3，且非全 1
        if all(0.3 <= v <= 3.0 for v in diag):
            if all(0 <= abs(v) <= 2.5 for v in offd):
                # 排除纯 gamma/增益(全是 0-1)
                if max(abs(v) for v in c) > 0.4:
                    cands.append((off, c))
    # 合并相邻(同一数组多行)
    merged = []
    for off, c in cands:
        # 每 3 个浮点可能对应不同组，按 9 浮点去重去杂乱
        pass
    return cands

if __name__ == '__main__':
    import os
    base = "/home/stray/camera-work/win_cam_driver/code$GetExtractPath$"
    for fn in sys.argv[1:] or ['OV5678_CJFK520_TGL.aiqb','gc5035_CJAK519_TGL.aiqb']:
        p = os.path.join(base, fn)
        if not os.path.exists(p): 
            print("skip", p); continue
        data = parse(p)

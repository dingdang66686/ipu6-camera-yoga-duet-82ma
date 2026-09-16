#!/usr/bin/env python3
"""扫描 aiqb 全部 float32，找 3x3 CCM 候选（行和≈1的9元组）与 AWB 增益候选。"""
import struct, os, sys

base = "/home/stray/camera-work/win_cam_driver/code$GetExtractPath$"

def floats(data, off, n):
    return struct.unpack_from('<%df'%n, data, off)

def is_ccm(c, tol=0.35):
    """3x3 CCM: 每行和≈1, 对角主导, 值范围合理。"""
    if any(not (-0.5 < v < 4.0) for v in c): return False
    rows = [sum(c[0:3]), sum(c[3:6]), sum(c[6:9])]
    if not all(abs(r-1.0) < tol for r in rows): return False
    diag = [c[0],c[4],c[8]]
    if not all(v > 0.3 for v in diag): return False
    # 对角应明显大于非对角典型
    return True

def is_rgb_gain(c, tol=0.2):
    """AWB 增益: 每行 1 个主值 + 2 个近0。"""
    for r in range(3):
        row = c[r*3:(r+1)*3]
        mx = max(abs(x) for x in row)
        if not any(abs(x-mx)<tol for x in row): return False
        if not all(x==0 or abs(x)<0.15 or abs(x-mx)<tol for x in row): return False
    return True

for fn in ['gc5035_CJAK519_TGL.aiqb','OV5678_CJFK520_TGL.aiqb']:
    p=os.path.join(base,fn)
    data=open(p,'rb').read()
    n=len(data)
    print(f"\n===== {fn} ({n} bytes) =====")
    ccm=0; wb=0
    for off in range(0xf0, n-36, 4):
        c=floats(data,off,9)
        if not all(-5<v<100 for v in c): continue
        if is_ccm(c):
            print(f"  [CCM?] off=0x{off:x}  "
                  f"[{', '.join('%.3f'%v for v in c)}]")
            ccm+=1
    print(f"  CCM 候选数: {ccm}")

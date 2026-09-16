#!/usr/bin/env python3
"""严格 CCM 扫描: 行和≈1 + 每行有负元素(强特征) + 对角主导"""
import struct, os

base = "/home/stray/camera-work/win_cam_driver/code$GetExtractPath$"
def floats(d,o,n): return struct.unpack_from('<%df'%n,d,o)

def rowsum(c,r): return sum(c[r*3:(r+1)*3])

for fn in ['gc5035_CJAK519_TGL.aiqb','OV5678_CJFK520_TGL.aiqb']:
    d=open(os.path.join(base,fn),'rb').read()
    n=len(d)
    print(f"\n===== {fn} — 行和≈1 且每行含负数(典型CCM) =====")
    hits=0
    for off in range(0xf0,n-36,4):
        c=floats(d,off,9)
        if not all(-3<v<4 for v in c): continue
        rows=[rowsum(c,0),rowsum(c,1),rowsum(c,2)]
        if not all(abs(r-1.0)<0.15 for r in rows): continue
        # 每行有负元素(典型 CCM 的交叉项)
        neg = (any(v < -0.02 for v in c[0:3])
               and any(v < -0.02 for v in c[3:6])
               and any(v < -0.02 for v in c[6:9]))
        if not neg: continue
        print(f"  off=0x{off:x}: [{', '.join('%.4f'%v for v in c)}]  rows({','.join('%.2f'%r for r in rows)})")
        hits+=1
        if hits>30: print("  ...(截断)"); break
    print(f"  hit={hits}")

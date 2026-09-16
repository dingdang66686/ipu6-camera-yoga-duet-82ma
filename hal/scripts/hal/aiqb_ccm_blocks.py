#!/usr/bin/env python3
"""
精确识别真 CCM 块: 前导 4-float 白点/参考(各∈[0.3,1.0]) + 紧随 3x3 CCM(行和=1, 对角>0.5, 每行有负)。
白点参考: 形如 [R,G,B,?] 四值均在 0.3~1.0 且(通常)非全相等。
"""
import struct, os
base="/home/stray/camera-work/win_cam_driver/code$GetExtractPath$"
def floats(d,o,n): return struct.unpack_from('<%df'%n,d,o)

def is_ref4(v):
    return all(0.3<=abs(x)<=1.2 for x in v)

def is_ccm9(c):
    if not all(-4<v<4 for v in c): return False
    rows=[sum(c[0:3]),sum(c[3:6]),sum(c[6:9])]
    if not all(abs(r-1.0)<0.12 for r in rows): return False
    if not all(c[i]>0.5 for i in (0,4,8)): return False
    return (any(v<-0.02 for v in c[0:3]) and any(v<-0.02 for v in c[3:6])
            and any(v<-0.02 for v in c[6:9]))

for fn in ['gc5035_CJAK519_TGL.aiqb','OV5678_CJFK520_TGL.aiqb']:
    d=open(os.path.join(base,fn),'rb').read(); n=len(d)
    blocks=[]
    off=0xf0
    while off < n-52:
        # 前导 4 float 是白点参考，且后面紧跟 9 float CCM
        ref=floats(d,off,4)
        if is_ref4(ref):
            c=floats(d,off+16,9)
            if is_ccm9(c):
                # 追加一个检查: 该 4 float 至少不全是 0.5/0.5 之类 (排除 LUT)
                blocks.append((off,ref,c))
                off+=52  # 4+9 float + 前进
                continue
        off+=4
    print(f"\n===== {fn}: {len(blocks)} 个 <白点+CCM> 块 =====")
    for i,(off,ref,c) in enumerate(blocks):
        print(f"\n  块{i} @0x{off:06x}")
        print(f"    白点/参考 f32: {['%.4f'%v for v in ref]}")
        print(f"    CCM: {['%.4f'%v for v in c]}")

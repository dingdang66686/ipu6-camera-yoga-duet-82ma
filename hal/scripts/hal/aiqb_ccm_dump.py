#!/usr/bin/env python3
"""
从 Intel aiqb (CPFF) 完整提取所有独立 CCM 矩阵(3x3, 行和=1) 及相邻参数。
输出：每个 CCM 簇 + 其前导 float/整数 + 后继 12 float (下个矩阵)。
用于确认行序与色温档。
"""
import struct, os

base="/home/stray/camera-work/win_cam_driver/code$GetExtractPath$"
def floats(d,o,n): return struct.unpack_from('<%df'%n,d,o)
def u32(d,o): return struct.unpack_from('<I',d,o)[0]

def is_ccm(c):
    if not all(-4<v<4 for v in c): return False
    rows=[sum(c[0:3]),sum(c[3:6]),sum(c[6:9])]
    if not all(abs(r-1.0)<0.12 for r in rows): return False
    # 对角>0.5 且每行有负
    if not all(c[i]>0.5 for i in (0,4,8)): return False
    return (any(v<-0.02 for v in c[0:3]) and any(v<-0.02 for v in c[3:6])
            and any(v<-0.02 for v in c[6:9]))

for fn in ['gc5035_CJAK519_TGL.aiqb','OV5678_CJFK520_TGL.aiqb']:
    d=open(os.path.join(base,fn),'rb').read()
    n=len(d)
    # 找所有起点(簇起始)
    starts=[]
    off=0xf0
    while off < n-36:
        if is_ccm(floats(d,off,9)):
            starts.append(off)
            off+=36   # 跳到下个独立矩阵
        else:
            off+=4
    print(f"\n{'='*74}\n{fn}  发现 {len(starts)} 个独立 CCM")
    for i,s in enumerate(starts):
        c=floats(d,s,9)
        # 前导: 往前最多 0x40, 收集 3 个 float 候选
        # 打印前 16 byte float 和前 16 byte uint
        preF = struct.unpack_from('<4f', d, s-16) if s>=16 else None
        preU = struct.unpack_from('<4I', d, s-16) if s>=16 else None
        print(f"\n  CCM[{i}] @0x{s:06x}:")
        print(f"    矩阵: {['%.4f'%v for v in c]}")
        print(f"    行和: {['%.3f'%sum(c[j:j+3]) for j in (0,3,6)]}")
        if preF:
            print(f"    前16B f32: {['%.4f'%v for v in preF]}   u32: {['0x%x'%v for v in preU]}")

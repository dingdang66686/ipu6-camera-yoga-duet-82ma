#!/usr/bin/env python3
"""提取 aiqb 中的独立 CCM(36字节不重叠) + 周边上下文(找色温/块头)"""
import struct, os

base="/home/stray/camera-work/win_cam_driver/code$GetExtractPath$"
def floats(d,o,n): return struct.unpack_from('<%df'%n,d,o)
def u32(d,o): return struct.unpack_from('<I',d,o)[0]

def is_ccm(c):
    if not all(-4<v<4 for v in c): return False
    rows=[sum(c[0:3]),sum(c[3:6]),sum(c[6:9])]
    if not all(abs(r-1.0)<0.15 for r in rows): return False
    return (any(v<-0.02 for v in c[0:3]) and any(v<-0.02 for v in c[3:6])
            and any(v<-0.02 for v in c[6:9]))

for fn in ['gc5035_CJAK519_TGL.aiqb','OV5678_CJFK520_TGL.aiqb']:
    d=open(os.path.join(base,fn),'rb').read()
    n=len(d)
    print(f"\n{'='*72}\n{fn}")
    # 找所有满足 is_ccm 的偏移
    starts=[]
    for off in range(0xf0,n-36,4):
        if is_ccm(floats(d,off,9)):
            starts.append(off)
    # 去重: 相邻差<36 的合并(取每个簇的最小为起点)
    clusters=[]
    for s in starts:
        if clusters and s-clusters[-1][-1] < 36:
            clusters[-1].append(s)
        else:
            clusters.append([s])
    print(f"找到 {len(starts)} 个滑动命中, {len(clusters)} 个簇(独立矩阵)")
    for cl in clusters:
        s0=cl[0]
        c=floats(d,s0,9)
        # 向前找可能的 CCT/块头: 往前 0x40 看 uint32
        # 打印该矩阵
        print(f"\n  CCM @0x{s0:x} (簇 {len(cl)} 命中):")
        print(f"    [{' , '.join('%.4f'%v for v in c)}]")
        # 行和
        print(f"    rows=({', '.join('%.3f'%sum(c[i*3:i*3+3]) for i in range(3))})")
        # 打印前 20 bytes 上下文 (uint32 + float)
        pre=d[max(0,s0-0x20):s0]
        preu=struct.unpack_from('<%dI'%(len(pre)//4),pre,0) if len(pre)>=4 else ()
        print(f"    前文 uint32: {[hex(x) for x in preu]}")
        # 后 12 float 看看是否连续第2组
        after=floats(d,s0+36,12) if s0+36+48<=n else None
        print(f"    后继12float(前几法第二矩阵?): {['%.3f'%v for v in after[:9]] if after else None}")

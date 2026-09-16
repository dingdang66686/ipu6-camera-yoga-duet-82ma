#!/usr/bin/env python3
"""
从 Intel aiqb (CPFF) 提取 <白点参考 + 3x3 CCM> 块，并输出可读记录 + 按 R/B 排序。
白点格式: 4-float [X,Y,uv?,uv?]，前两值反映 R/B 增益（暖: R大B小, 冷: R小B大）。
输出保存到 aiqb_ccm_extracted.txt
"""
import struct, os, json
base="/home/stray/camera-work/win_cam_driver/code$GetExtractPath$"
def floats(d,o,n): return struct.unpack_from('<%df'%n,d,o)
def is_ref4(v): return all(0.3<=abs(x)<=1.2 for x in v)
def is_ccm9(c):
    if not all(-4<v<4 for v in c): return False
    rows=[sum(c[0:3]),sum(c[3:6]),sum(c[6:9])]
    if not all(abs(r-1.0)<0.12 for r in rows): return False
    if not all(c[i]>0.5 for i in (0,4,8)): return False
    return (any(v<-0.02 for v in c[0:3]) and any(v<-0.02 for v in c[3:6]) and any(v<-0.02 for v in c[6:9]))

def extract(fn):
    d=open(os.path.join(base,fn),'rb').read(); n=len(d)
    blocks=[]; off=0xf0
    seen=set()
    while off < n-52:
        ref=floats(d,off,4)
        if is_ref4(ref):
            c=floats(d,off+16,9)
            if is_ccm9(c):
                key=tuple(round(x,3) for x in c)
                if key not in seen:
                    seen.add(key)
                    blocks.append((off,ref,c))
                off+=52; continue
        off+=4
    return blocks

out=[]
for fn in ['gc5035_CJAK519_TGL.aiqb','OV5678_CJFK520_TGL.aiqb']:
    blocks=extract(fn)
    # 去重后按 R/B 白点比排序(暖→冷): 取 ref[0] 大=暖
    blocks_sorted=sorted(blocks, key=lambda b:-b[1][0])
    out.append((fn,blocks_sorted))

with open('/home/stray/camera-work/aiqb_ccm_extracted.txt','w') as f:
    for fn,blocks in out:
        f.write(f"\n{'='*70}\n{fn}  共 {len(blocks)} 个独立 CCM 块(按白点R/B 暖→冷排序)\n")
        for i,(off,ref,c) in enumerate(blocks):
            f.write(f"\n  [{i}] @0x{off:06x}\n")
            f.write(f"      白点(参考): R/G?,B/G? : {['%.4f'%v for v in ref]}\n")
            f.write(f"      CCM(3x3):  {['%.4f'%v for v in c]}\n")
            f.write(f"        行和: {['%.3f'%sum(c[j:j+3]) for j in (0,3,6)]}\n")
    # 同时 JSON 保存便于程序化
open('/home/stray/camera-work/aiqb_ccm_extracted.json','w').write(json.dumps(
    {fn:[{'off':b[0],'ref':b[1],'ccm':b[2]} for b in blocks] for fn,blocks in out}, indent=1))

print("已写入 aiqb_ccm_extracted.txt / .json")
for fn,blocks in out:
    print(f"\n{fn}: {len(blocks)} 块；D65档(白点B/R平衡接近)候选:")
    # 打印 ref 前两项比值 R/B
    for i,b in enumerate(blocks):
        ref=b[1]
        print(f"  [{i}] ref={['%.3f'%v for v in ref]}  ratio={ref[1]/max(ref[0],1e-6):.2f}")

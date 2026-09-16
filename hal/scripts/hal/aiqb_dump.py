#!/usr/bin/env python3
"""深挖 aiqb: 精确 dump 头部块结构 + 定位 float 矩阵候选"""
import struct, sys, os

def u32(b,o): return struct.unpack_from('<I', b, o)[0]
def f32(b,o): return struct.unpack_from('<f', b, o)[0]

base = "/home/stray/camera-work/win_cam_driver/code$GetExtractPath$"

def hexdump(b, off, length, per=16):
    lines=[]
    for i in range(0,length,per):
        chunk=b[off+i:off+i+per]
        hexs=' '.join(f'{x:02x}' for x in chunk)
        asc=''.join(chr(x) if 32<=x<127 else '.' for x in chunk)
        lines.append(f"{off+i:06x}  {hexs:<{per*3}}  {asc}")
    return '\n'.join(lines)

for fn in sys.argv[1:] or ['gc5035_CJAK519_TGL.aiqb','OV5678_CJFK520_TGL.aiqb']:
    p=os.path.join(base,fn)
    if not os.path.exists(p): 
        print("skip",p); continue
    data=open(p,'rb').read()
    print(f"\n{'='*70}\n{fn}  ({len(data)} bytes)")
    print(hexdump(data,0,0x140,16))

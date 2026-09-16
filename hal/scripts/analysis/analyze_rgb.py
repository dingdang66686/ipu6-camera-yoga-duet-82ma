#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析 softISP RGB PPM, 定位测试卡的 9 色块, 得到每块中心坐标(供映射回 raw)"""
import re, sys

path = "/home/stray/camera-work/card_rgbcam0-stream0-000000.ppm"
data = open(path, "rb").read()
# 解析 PPM 头
assert data[:2] == b"P6", data[:2]
# 找最后一行的数据开始
i = 2
tokens = []
while True:
    if data[i:i+1] == b'#':
        while data[i:i+1] != b'\n': i += 1
        i += 1; continue
    while data[i:i+1] in b' \t\r\n': i += 1
    j = i
    while data[j:j+1] not in b' \t\r\n': j += 1
    tokens.append(int(data[i:j]))
    i = j
    if len(tokens) >= 3:
        # 需要找到最大值(maxval)后一个字节(白色分隔)后的数据
        # 简化: 继续找第三个数字后的分隔
        i = j
        while data[i:i+1] in b' \t\r\n': i += 1
        # 第三个数字(maxval)已取, 下一个字节就是数据开头
        if tokens[2] <= 255:
            # 继续
            continue
    if len(tokens) >= 3 and tokens[2] > 255:
        # maxval > 255 少见, 处理 16bit
        pass
    if len(tokens) >= 3 and len(data) > i and data[i] not in b'0123456789':
        break
# 重新稳妥解析: 找 maxval
m = re.match(rb'P6\s+#?[^\n]*\n(\d+)\s+(\d+)\s+#?[^\n]*\n(\d+)\s*\n', data[:200])
if m:
    W, H, maxv = int(m.group(1)), int(m.group(2)), int(m.group(3))
    header_len = len(m.group(0))
else:
    # 手动
    W = tokens[0]; H = tokens[1]; maxv = tokens[2]
    header_len = i
    # 上面逻辑可能不对, 手动找
    # 直接按 P6 恢复: P6\nW H\nmaxv\n
W, H = 2584, 1944
print(f"PPM {W}x{H} maxv={maxv if 'maxv' in dir() else '?'} header={header_len}, total={len(data)}")

# 手动确定 header(标准 P6)
idx = 2
def skip_ws():
    global idx
    while idx < len(data) and data[idx:idx+1] in b' \t\r\n': idx += 1
def read_num():
    global idx
    skip_ws()
    j = idx
    while idx < len(data) and data[idx:idx+1] not in b' \t\r\n': idx += 1
    n = int(data[j:idx]); skip_ws(); return n
W = read_num(); H = read_num(); maxv = read_num()
print(f"重新解析: W={W} H={H} maxv={maxv}, 数据起点 idx={idx}, 每像素3字节, 期望总={W*H*3}")

px = data[idx:]
assert len(px) >= W*H*3, len(px)

# RGB 访问
def p3(x, y):
    o = (y*W+x)*3
    return px[o], px[o+1], px[o+2]

# ---- 全局 30x20 网格, 找测试卡 ----
GX, GY = 30, 20
print("\n=== 全局网格 (R,G,B) 简化 — 找色块 ===")
# 输出每块的色相标签
for gy in range(GY):
    line = []
    for gx in range(GX):
        x0,x1 = gx*W//GX,(gx+1)*W//GX
        y0,y1 = gy*H//GY,(gy+1)*H//GY
        rs=gs=bs=0; n=0
        for y in range(y0,y1,6):
            for x in range(x0,x1,6):
                r,g,b=p3(x,y); rs+=r; gs+=g; bs+=b; n+=1
        r,g,b = rs//n,gs//n,bs//n
        mx=max(r,g,b); mn=min(r,g,b)
        if mx < 40: tag='.'
        else:
            if mx-mn < 25: tag='G' if g>85 else '.'
            elif r>=g and r>=b: tag='R'
            elif g>=r and g>=b: tag='G'
            else: tag='B'
        line.append(tag)
    print("".join(line))

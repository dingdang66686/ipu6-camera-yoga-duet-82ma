#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析测试卡 raw: 自动检测纯色块, 对每块做 4x4 CFA 相位统计, 锁定 IR 像素"""
W, H = 2592, 1944
path = "/home/stray/camera-work/card.raw"

def read_raw():
    data = open(path, "rb").read()
    px = [0]*(W*H)
    for i in range(W*H):
        b0 = data[i*2]; b1 = data[i*2+1]
        px[i] = (b0 | (b1<<8)) & 0x3FF
    return px
px = read_raw()
def g(x, y):
    if 0 <= x < W and 0 <= y < H: return px[y*W+x]
    return 0
print(f"读取 {len(px)} px, min={min(px)} max={max(px)} mean={sum(px)//len(px)}")

# ---- 1. 全局采样找画面大致颜色分区 (粗网格均值) ----
# 屏幕显示测试卡在画面中央, 先看全局 20x15 块均值找画面分布
import math
GX, GY = 30, 20
grid = []
for gy in range(GY):
    row = []
    for gx in range(GX):
        x0, x1 = gx*W//GX, (gx+1)*W//GX
        y0, y1 = gy*H//GY, (gy+1)*H//GY
        vals = [g(x,y) for y in range(y0,y1,6) for x in range(x0,x1,6)]
        row.append((sum(vals)//len(vals), max(vals), min(vals)))
    grid.append(row)

print("\n=== 全局 30x20 网格 (均值) — 找测试卡位置 ===")
for row in grid:
    print(" ".join(f"{v:4d}" for v,_,_ in row))

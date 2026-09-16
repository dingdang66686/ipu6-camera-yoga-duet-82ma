#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析 OV5678 test pattern (Standard Color Bar) raw,
反推 4x4 RGB-IR CFA 排列。
raw 格式: 2592x1944, 2 字节/像素 小端, 值 = b0 | b1<<8 & 0x3FF
"""
import sys, struct

W, H = 2592, 1944
path = "/home/stray/camera-work/testpat.raw"

def read_raw():
    data = open(path, "rb").read()
    assert len(data) == W*H*2, f"size={len(data)}"
    # 每行 2 字节/像素小端
    px = [0]*(W*H)
    for i in range(W*H):
        b0 = data[i*2]; b1 = data[i*2+1]
        px[i] = (b0 | (b1<<8)) & 0x3FF
    return px

px = read_raw()
print(f"读取完成 {len(px)} 像素, max={max(px)} min={min(px)}")

def get(x, y):
    if 0 <= x < W and 0 <= y < H:
        return px[y*W+x]
    return 0

# ---- 1. 整幅颜色分区概览: 采样网格看不同颜色数量/位置 ----
from collections import Counter
cnt = Counter()
# 每 16px 采样一次
for y in range(0, H, 16):
    for x in range(0, W, 16):
        v = get(x, y) // 16   # 粗量化
        cnt[(x//(W//8), v)] += 1
# 统计每 1/8 水平列的电平分布(均值)
col_stats = []
for c in range(8):
    vals = []
    for y in range(0, H, 8):
        for x in range(c*(W//8), (c+1)*(W//8), 8):
            vals.append(get(x, y))
    col_stats.append((sum(vals)/len(vals), min(vals), max(vals)))
print("\n=== 水平 1/8 列电平均值 (判断彩条色带分布) ===")
for i,(m,mi,ma) in enumerate(col_stats):
    print(f"列{i}: 均值={m:6.1f} min={mi} max={ma}")

# ---- 2. 4x4 CFA 相位均值 (用全图或指定区) ----
# 先取中间水平条纹最丰富的区域: 遍扫各 8 块水平列做 4x4 相位
print("\n=== 各水平色带的 4x4 相位均值 (每相位 = icol_offset) ===")
def phase_means(x0, x1, y0, y1):
    acc = [[0]*4 for _ in range(4)]
    n = [[0]*4 for _ in range(4)]
    for yy in range(y0, y1):
        for xx in range(x0, x1):
            r = yy & 3; c = xx & 3
            acc[r][c] += get(xx, yy); n[r][c] += 1
    out = [[0.0]*4 for _ in range(4)]
    for r in range(4):
        for c in range(4):
            out[r][c] = acc[r][c]/n[r][c]
    return out

def show(m):
    for r in range(4):
        row = " ".join(f"{m[r][c]:6.0f}" for c in range(4))
        print("  " + row)

# 分析右侧 6 列 (通常彩条彩色带), 竖直取中间区域
print("\n--- 右侧色带区 (x 1960~2592, 垂直中段) 4x4 相位 ---")
show(phase_means(1960, 2592, 500, 1400))

# 分析左端 (通常彩条第一带是白/灰)
print("\n--- 左端色带区 (x 0~300, 垂直中段) 4x4 相位 ---")
show(phase_means(0, 300, 500, 1400))

# ---- 3. 相位显著度: 对整幅图各相位 vs 平均 ----
print("\n--- 整幅图 4x4 相位均值 (找出偏离平均的相位=可能IR) ---")
full = phase_means(0, W, 0, H)
show(full)
all_m = [full[r][c] for r in range(4) for c in range(4)]
overall = sum(all_m)/len(all_m)
print(f"  整体均值 {overall:.1f}")
print("  偏离>5%整体的相位 (潜在IR):")
for r in range(4):
    for c in range(4):
        dev = (full[r][c]-overall)/overall*100
        if abs(dev) > 5:
            print(f"    ({r},{c}) = {full[r][c]:.1f}  偏差 {dev:+.1f}%")

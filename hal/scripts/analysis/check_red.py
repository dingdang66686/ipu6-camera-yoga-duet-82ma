#!/usr/bin/env python3
"""检查受控曝光下红色屏 fixed_red.raw 的饱和率与相位响应。"""
import statistics

W, H = 2592, 1944


def read_raw(path):
    data = open(path, 'rb').read()
    px = [[0] * W for _ in range(H)]
    for y in range(H):
        row = data[y * 2 * W:(y + 1) * 2 * W]
        for x in range(W):
            px[y][x] = (row[x * 2] | row[x * 2 + 1] << 8) & 0x3FF
    return px


def screen_center(px, th=120):
    xs, ys = [], []
    for y in range(0, H, 8):
        for x in range(0, W, 8):
            if px[y][x] > th:
                xs.append(x)
                ys.append(y)
    if not xs:
        return W // 2, H // 2
    return int(statistics.median(xs)), int(statistics.median(ys))


px = read_raw("fixed_red.raw")
cx, cy = screen_center(px)
print(f"红色屏 屏幕中心=({cx},{cy})")

# 屏幕中心 ROI 400x400 分析与饱和率
ROI = 400
ox, oy = cx - ROI // 2, cy - ROI // 2
allv = []
sat = 0
ph = [[[] for _ in range(4)] for __ in range(4)]
for y in range(oy, oy + ROI):
    for x in range(ox, ox + ROI):
        v = px[y][x]
        allv.append(v)
        if v >= 1023:
            sat += 1
        ph[y & 3][x & 3].append(v)

total = len(allv)
print(f"屏心 ROI {ROI}x{ROI}: 饱和率 = {sat/total*100:.1f}%  ({sat}/{total})")
print(f"全均值 = {statistics.mean(allv):.0f}  最大 = {max(allv)}")

print("\n4x4 绝对相位均值（应红相位(R)最高）:")
for r in range(4):
    line = " ".join(f"{round(statistics.mean(ph[r][c])):5d}" for c in range(4))
    print("   " + line)

# 统计各相位均值，打印排序定位红相位
print("\n各相位可见度排序:")
items = []
for r in range(4):
    for c in range(4):
        items.append((statistics.mean(ph[r][c]), r, c))
items.sort(reverse=True)
for m, r, c in items:
    print(f"  相位({r},{c}) 均值={round(m)}")

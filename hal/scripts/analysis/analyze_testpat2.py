#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""精确定位右半区"异常亮点"的空间分布, 判断是否形成4x4 IR子格"""
W, H = 2592, 1944
path = "/home/stray/camera-work/testpat.raw"

def read_raw():
    data = open(path, "rb").read()
    px = [0]*(W*H)
    for i in range(W*H):
        b0 = data[i*2]; b1 = data[i*2+1]
        px[i] = (b0 | (b1<<8)) & 0x3FF
    return px
px = read_raw()
def get(x, y):
    return px[y*W+x]

# 扫描右半区 x>2000 找 >200 的亮点, 记录其 (x,y) 及相位
import collections
# 按 4x4 相位统计命中数
phase_cnt = collections.Counter()
pts = []
for y in range(0, H):
    for x in range(2000, W):
        v = get(x, y)
        if v > 200:
            phase_cnt[(y & 3, x & 3)] += 1
            if len(pts) < 2000:
                pts.append((x, y, v))

print("=== 右半区(x>2000) v>200 亮点的 4x4 相位命中分布 ===")
for r in range(4):
    row = " ".join(f"{(r,c)}:{phase_cnt.get((r,c),0):5d}" for c in range(4))
    print("  " + row)
tot = sum(phase_cnt.values())
print(f"总亮点数: {tot}")

# 看这些亮点是否集中某几行/列(水平条纹?)
if pts:
    xs = sorted(set(p[0] for p in pts)); ys = sorted(set(p[1] for p in pts))
    print(f"x范围: {xs[0]}..{xs[-1]}, 不同x数={len(xs)}")
    print(f"y范围: {ys[0]}..{ys[-1]}, 不同y数={len(ys)}")
    print("前20个(x,y,v):", pts[:20])

# 检查整幅图的 min=64 是否均匀的黑底, 找出过渡边界 x
print("\n=== 整幅垂直中线每 100 行: 找白->黑的水平过渡边界 ===")
for y in range(0, H, 200):
    # 找该行第一个 <900 的 x
    edge = None
    for x in range(0, W):
        if get(x, y) < 900:
            if x > 400:
                edge = x; break
    print(f"y={y}: 白->黑边界 x≈{edge}")

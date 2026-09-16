#!/usr/bin/env python3
"""
生成一张用于反推 OV5678 4x4 RGB-IR CFA 排列的测试卡样图。

设计原理:
  OV5678 是 4x4 RGB-IR 传感器（25% IR 像素 + 75% R/G/B 像素，官方未公开 IR 坐标）。
  我们要从 raw 帧反推 IR 像素位置 -> 需要一张"已知颜色、大块纯色"的测试卡，
  相机拍下后对比每个 4x4 相位在已知色块下的响应差异，即可锁定哪些相位是 IR。

  这里生成一张包含大量纯色块 + 色阶 + 网格的测试卡，输出 PPM，再用 ImageMagick 转 PNG。

用法:
  python3 gen_testcard.py            # 生成 testcard.ppm + testcard.png (全尺寸 2592x1944)
  python3 gen_testcard.py OUT.png    # 指定输出文件
"""

import sys
import subprocess
import os

W, H = 2592, 1944


def clamp(v):
    return max(0, min(255, int(v)))


def write_ppm(path, w, h, get_pixel):
    """get_pixel(x, y) -> (r,g,b)"""
    data = bytearray(w * h * 3)
    i = 0
    for y in range(h):
        for x in range(w):
            r, g, b = get_pixel(x, y)
            data[i] = clamp(r); data[i+1] = clamp(g); data[i+2] = clamp(b)
            i += 3
    with open(path, "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % (w, h))
        f.write(data)


def make_testcard():
    # ---- 定义一系列"已知纯色"色块，每个至少覆盖 >30x30 像素（保证 raw 相位可分析） ----
    # 名字: (r,g,b)  —— 都取"最纯"的 RGB，让去马赛克后各相位响应差异最大化
    colors = [
        ("R",   (255, 0, 0)),
        ("G",   (0, 255, 0)),
        ("B",   (0, 0, 255)),
        ("C",   (0, 255, 255)),
        ("Y",   (255, 255, 0)),
        ("M",   (255, 0, 255)),
        ("W",   (255, 255, 255)),
        ("Gray",(128, 128, 128)),
        ("K",   (0, 0, 0)),
    ]
    # 顶部色块行：9 个正方形，每块宽 = W//9，高 = H//3
    block_w = W // 9
    block_h = H // 3

    def get_pixel(x, y):
        # 顶部：纯色块行（用于定位 IR 像素：对比同色下各 4x4 相位）
        if y < block_h:
            idx = min(8, x // block_w)
            return colors[idx][1]
        # 中间：垂直 RGB 渐变条（帮助判断色相连续性）
        if y < 2 * block_h:
            yy = (y - block_h) / block_h
            band = int(x // (W // 3))
            if band == 0:   # R -> 白 渐变（带G/B分量，产生彩色过渡）
                return (255, int(255 * yy), int(255 * yy))
            elif band == 1: # 灰阶
                return (int(255 * yy),) * 3
            else:           # B -> 黄
                return (int(255 * yy), int(255 * yy), 255)
        # 底部：白底 + 细网格（用于检查空间精度/对齐）
        g = (x // 32 + y // 32) % 2
        return (200, 200, 200) if g else (60, 60, 60)

    return get_pixel


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "testcard.png"
    base = os.path.splitext(out)[0]
    ppm = base + ".ppm"
    print(f"生成测试卡 PPM: {ppm}  ({W}x{H})")
    write_ppm(ppm, W, H, make_testcard())
    subprocess.run(["magick", ppm, out], check=True)
    # 再生成一张缩小预览方便查看
    subprocess.run(["magick", out, "-resize", "1296x", base + "_small.png"], check=True)
    print(f"完成: {out}")
    print(f"缩略预览: {base}_small.png")


if __name__ == "__main__":
    main()

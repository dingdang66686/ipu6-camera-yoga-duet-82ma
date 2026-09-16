#!/usr/bin/env python3
"""
OV5678 RGB-IR 分离工具（纯 Python，无 numpy/PIL）

实证确认的 IR 像素位置（4x4 块内）：
    IR 相位 = (r 偶, c 奇) = (0,1),(0,3),(2,1),(2,3)
    其余 12 个为 RGB 像素。

功能：
  1) IR 图：从 raw 抽出 4 个 IR 相位像素（1/4 采样 = 1296x972），
     双线性插值回满幅 2592x1944，输出 PPM/PNG。
  2) （可选）彩色占位：先不做完整 demosaic，把 IR 像素去掉留空供后续填。

用法：
  python3 separate_ir.py out.raw out_prefix          # 分离 IR 图
  # 生成 out_prefix_ir.ppm / out_prefix_ir.png
"""
import sys
import subprocess

W, H = 2592, 1944          # 全幅 raw 尺寸
IRW, IRH = W // 2, H // 2  # 1269x972? 实际 (W//2) 不对，下面按 1/4 采样网格算

# 简化：IR 相位在 (r 偶, c 奇)。从全幅坐标 (y,x) 中挑出
# y%2==0 and x%2==1 的位置。每 2x2 有 1 个 IR -> IR 采样网格为 (H/2, W/2)。

def clamp(v, lo=0, hi=1023):
    return max(lo, min(hi, int(v))) if v >= 0 else 0


def read_raw(path):
    data = open(path, "rb").read()
    n = W * H
    if len(data) < n * 2:
        raise SystemExit(f"raw 太小：{len(data)} < {n*2} 字节")
    # 返回 2D 数组 pixels[y][x]
    px = [[0] * W for _ in range(H)]
    for y in range(H):
        row = data[y * 2 * W:(y + 1) * 2 * W]
        for x in range(W):
            px[y][x] = (row[x * 2] | row[x * 2 + 1] << 8) & 0x3FF
    return px


def extract_ir_grid(px):
    """从全幅 raw 抽出 IR 像素，排成 IRH x IRW(=H/2 x W/2) 采样网格。
    IR 相位 y%2==0, x%2==1。"""
    ir = [[0] * (W // 2) for _ in range(H // 2)]
    for gy in range(H // 2):
        y = gy * 2            # y%2==0 的行
        for gx in range(W // 2):
            x = gx * 2 + 1    # x%2==1 的列
            ir[gy][gx] = px[y][x]
    return ir


def zero_pad(px, ir_mask, y, x):
    """返回 (y,x) 处像素值，若越界回 clamp；用于插值边界。"""
    y = 0 if y < 0 else (H - 1 if y >= H else y)
    x = 0 if x < 0 else (W - 1 if x >= W else x)
    return px[y][x]


def fullscale_ir(px):
    """把 1/4 采样 IR 网格双线性插值成满幅 IR 值表（仅 IR 相位处的值用于输出图）。
    我们实际上对每个 (y,x)（无论相位）都用最近 2x2 内的 IR 采样插值，
    得到每个输出像素的 IR 估计。"""
    irs = extract_ir_grid(px)
    irh, irw = H // 2, W // 2
    irfull = [[0] * W for _ in range(H)]
    # 对每个 IR 采样点 (gy,gx) 映射到全幅(2*gy, 2*gx+1)，做双线性填到相邻输出像素。
    # 简单方案：构造满幅 IR 图，每个全幅像素用其所在 2x2 IR 采样块的双线性值。
    for y in range(H):
        fy = (y // 2)          # 最近 IR 网格行（向上取整也行，用最近邻 + 线性）
        y0 = (y // 2)          # IR 网格 y 索引
        ty = (y % 2) / 2.0     # 该输出行在 IR 单元内的比例 [0,1)
        y1 = min(y0 + 1, irh - 1)
        for x in range(W):
            x0 = x // 2        # IR 网格 x 索引（IR 在 x%2==1）
            tx = (x % 2) / 2.0
            x1 = min(x0 + 1, irw - 1)
            v00 = irs[y0][x0]
            v10 = irs[y0][x1]
            v01 = irs[y1][x0]
            v11 = irs[y1][x1]
            top = v00 + (v10 - v00) * tx
            bot = v01 + (v11 - v01) * tx
            irfull[y][x] = top + (bot - top) * ty
    return irfull


def write_ppm(path, w, h, get):
    data = bytearray(w * h * 3)
    i = 0
    for y in range(h):
        for x in range(w):
            v = clamp(get(y, x), 0, 255)
            data[i] = data[i + 1] = data[i + 2] = v
            i += 3
    with open(path, "wb") as f:
        f.write(b"P6\n%d %d\n255\n" % (w, h))
        f.write(data)


def main():
    if len(sys.argv) < 3:
        print("用法: python3 separate_ir.py in.raw out_prefix")
        return
    src, prefix = sys.argv[1], sys.argv[2]
    print(f"读取 {src} ...")
    px = read_raw(src)
    print("提取 IR 像素并插值满幅 ...")
    irfull = fullscale_ir(px)

    ppm = f"{prefix}_ir.ppm"
    write_ppm(ppm, W, H, lambda y, x: irfull[y][x] / 1023 * 255)
    print(f"写 {ppm}")
    subprocess.run(["magick", ppm, f"{prefix}_ir.png"], check=True)
    print(f"写 {prefix}_ir.png")
    print("完成。请查看 IR 图确认是否抓到红外效果。")


if __name__ == "__main__":
    main()

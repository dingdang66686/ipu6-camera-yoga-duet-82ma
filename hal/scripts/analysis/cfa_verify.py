#!/usr/bin/env python3
"""
用「裁切后的纯净屏幕数据」重新验证/计算 4x4 CFA。

背景：之前 CFA 是用全幅(2582x1944)数据反推的，其中含大量屏幕外黑色背景，
且四张纯色图的屏幕在帧中位置可能不同。本脚本：
  1) 对每张 raw 自动检测屏幕亮区（亮度阈值），定位各自屏幕中心；
  2) 以各自屏幕中心裁切一个 ROI（默认 800x800），避开屏幕边缘与背景；
  3) 在 ROI 内对 4x4 绝对相位做原始值统计；
  4) 红/绿/蓝/白四图交叉比较，重新判定每个相位属于 R/G/B/IR。

用法：python3 cfa_verify.py [ROI_size]
按文件名规则读取 big_red.raw / big_green.raw / big_blue.raw / big_white.raw
"""
import sys, statistics

W, H = 2592, 1944
ROI = int(sys.argv[1]) if len(sys.argv) > 1 else 800
COL = {'red': '红', 'green': '绿', 'blue': '蓝', 'white': '白'}


def read_raw(path):
    data = open(path, 'rb').read()
    n = W * H
    if len(data) < n * 2:
        raise SystemExit(f"raw 太小：{len(data)} < {n*2}")
    px = [[0] * W for _ in range(H)]
    for y in range(H):
        row = data[y * 2 * W:(y + 1) * 2 * W]
        for x in range(W):
            px[y][x] = (row[x * 2] | row[x * 2 + 1] << 8) & 0x3FF
    return px


def screen_center(px, th=180):
    """亮度阈值找屏幕(亮区)质心与边界."""
    xs, ys = [], []
    for y in range(0, H, 8):
        for x in range(0, W, 8):
            if px[y][x] > th:
                xs.append(x)
                ys.append(y)
    if not xs:
        return W // 2, H // 2
    cx = int(statistics.median(xs))
    cy = int(statistics.median(ys))
    # 只保留围绕中值的亮区(去掉离群)再算一次粗边界
    return cx, cy


def main():
    print(f"ROI 尺寸 = {ROI}x{ROI}（每图各自检测屏幕中心）\n")
    # 每图: 屏幕中心 + 4x4 相位均值
    per_image = {}
    for name in ['red', 'green', 'blue', 'white']:
        px = read_raw(f"big_{name}.raw")
        cx, cy = screen_center(px)
        ox, oy = cx - ROI // 2, cy - ROI // 2
        # 4x4 绝对相位统计（ROI 内）
        ph = [[[] for _ in range(4)] for __ in range(4)]
        for y in range(oy, oy + ROI):
            for x in range(ox, ox + ROI):
                ph[y & 3][x & 3].append(px[y][x])
        means = [[round(statistics.mean(ph[r][c])) for c in range(4)] for r in range(4)]
        per_image[name] = (cx, cy, means)
        print(f"【{COL[name]}】屏幕中心=({cx},{cy})  裁切@{({ox},{oy})}")
        for r in range(4):
            print("   " + "  ".join(f"{means[r][c]:5d}" for c in range(4)))
        print()

    # 交叉判定：对每个相位，看红/绿/蓝三屏响应，判定通道
    print("=" * 50)
    print("按相对响应判定每个相位的通道（同一图内 R/B 比 + 跨图主色）")
    print("=" * 50)
    # 用同图内红蓝比(R/(R+B)) 判定 R/B，跨图综合判定 G/IR
    cand = {}
    for r in range(4):
        for c in range(4):
            R_ = per_image['red'][2][r][c]
            G_ = per_image['green'][2][r][c]
            B_ = per_image['blue'][2][r][c]
            W_ = per_image['white'][2][r][c]
            # 判 IR: 四色都显著暗于同图其他相位?  简化:用红绿蓝三图都低
            # 判 G: 绿屏特别高/三图都高
            # 判 R/B: 红蓝比
            rb = R_ + B_
            print(f"相位({r},{c})  红{R_:4d} 绿{G_:4d} 蓝{B_:4d} 白{W_:4d}  R/(R+B)={R_/(rb+1):.2f}  G相对(绿/(红+蓝))={(2*G_)/(R_+B_+1):.2f}")


if __name__ == '__main__':
    main()

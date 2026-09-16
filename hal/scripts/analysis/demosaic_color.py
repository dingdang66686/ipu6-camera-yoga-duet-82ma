#!/usr/bin/env python3
"""
OV5678 RGB-IR 彩色 demosaic + IR 分离（纯 Python，无 numpy/PIL）

实证确认的 4x4 CFA（大屏四色实验锁定）:
    (0,0)G (0,1)IR (0,2)G (0,3)IR
    (1,0)R (1,1)G  (1,2)B (1,3)G
    (2,0)G (2,1)IR (2,2)G (2,3)IR
    (3,0)B (3,1)G  (3,2)R (3,3)G
    = 4 IR + 8 G + 2 R + 2 B (彩色 G:R:B = 4:1:1)

功能：
  1) IR 图：抽 4 个 IR 相位(偶行,奇列)，双线性插回满幅 -> prefix_ir.ppm/png
  2) 彩色图：对每个像素做 R,G,B 三通道 IDW 插值(邻域 4x4 块同相位采样)，
     其中 IR 位置三通道全由邻近彩色像素插值 -> prefix_color.ppm/png

用法：
  python3 demosaic_color.py in.raw out_prefix [Rgain Bgain] [OW OH]

  默认先读全幅(2592x1944)再裁切传感器中心区域(居中 OW x OH)，避开边缘
  vignetting 与屏幕边缘色偏。默认 OW,OH = 1600 x 1200。
  Rgain/Bgain 不传时用 Default(1.0, 1.0 纯分离)。
"""
import sys, subprocess, statistics

W, H = 2592, 1944
OW, OH = 1200, 900    # 裁切尺寸（居中）
CX, CY = W // 2, H // 2   # 裁切中心（默认传感器中心；可指定为屏幕中心）
OX = CX - OW // 2     # 裁切左上角 x（绝对坐标）
OY = CY - OH // 2     # 裁切左上角 y（绝对坐标）

# 白平衡增益（R/B 相对 G）。纯分离(=1.0)先看效果。
# 受控曝光四色实测白屏 G:R:B = 236:174:174 -> 要白屏中性需拉平 R/B：
# WB_R = WB_B = 236/174 ≈ 1.36（用户确认白屏偏绿后启用）
WB_R_DEFAULT = 1.0
WB_B_DEFAULT = 1.0

# 是否对彩色输出做「亮度归一化」（默认关闭，用 --norm 开启）
# 解决"整体偏暗"：以裁切区 G 通道 p99.5 为参考白点，把 G 拉伸到接近满亮度，
# R/B 经 WB 增益跟随。纯色参考图上可显著提亮、且不破坏相对色调。
NORMALIZE = False

# 4x4 相位 -> 通道
PHASE = {
    (0,0):'G',(0,1):'I',(0,2):'G',(0,3):'I',
    (1,0):'R',(1,1):'G',(1,2):'B',(1,3):'G',
    (2,0):'G',(2,1):'I',(2,2):'G',(2,3):'I',
    (3,0):'B',(3,1):'G',(3,2):'R',(3,3):'G',
}
CHANS = 'RGB'


def read_raw(path):
    data = open(path, 'rb').read()
    n = W * H
    if len(data) < n * 2:
        raise SystemExit(f"raw 太小：{len(data)} < {n*2} 字节")
    px = [[0] * W for _ in range(H)]
    for y in range(H):
        row = data[y * 2 * W:(y + 1) * 2 * W]
        for x in range(W):
            px[y][x] = (row[x * 2] | row[x * 2 + 1] << 8) & 0x3FF
    return px


def auto_screen_center(px, th=180):
    """亮度阈值自动检测屏幕(亮区)质心。因每张 raw 屏幕位置可能不同，
    逐图检测可保证裁切都对准各自屏幕中心（避开背景与屏幕边缘）。"""
    xs, ys = [], []
    for y in range(0, H, 8):
        for x in range(0, W, 8):
            if px[y][x] > th:
                xs.append(x)
                ys.append(y)
    if not xs:
        return W // 2, H // 2
    return int(statistics.median(xs)), int(statistics.median(ys))


def extract_ir(px):
    """在裁切区 [OY,OY+OH) x [OX,OX+OW) 抽 IR(绝对偶行,奇列)，插值回满幅(裁切尺寸)。
    IR 位置 = 绝对坐标 (y%2==0, x%2==1)。用绝对坐标保证相位不随裁切偏移而错位。"""
    # 收集裁切区内 IR 采样到稠密网格(H/2 x W/2，用绝对坐标映射)
    gw, gh = (OW + 1) // 2, (OH + 1) // 2
    ir = [[0] * gw for _ in range(gh)]
    for y in range(OY, OY + OH):
        # 只在绝对偶行取
        if y % 2 != 0:
            continue
        gy = y // 2
        for x in range(OX, OX + OW):
            if x % 2 != 1:   # IR 在绝对奇列
                continue
            gx = x // 2
            if 0 <= gy < gh and 0 <= gx < gw:
                ir[gy][gx] = px[y][x]
    # 双线性插值回裁切区满幅（相对坐标回填）
    full = [[0] * OW for _ in range(OH)]
    for y in range(OH):
        # 该行绝对行 Ay; IR 采样绝对偶行 ay=2*gy
        ay = OY + y
        gy0 = ay // 2
        gy0 = max(0, min(gy0, gh - 1))
        gy1 = min(gy0 + 1, gh - 1)
        fy = ((ay // 2) - gy0) + (0.5 if ay % 2 == 0 else 0.0)
        # 简化: 用最近两 IR 行
        fy = 0.5 if ay % 2 == 1 else 0.0
        for x in range(OW):
            ax = OX + x
            # IR 绝对奇列
            gx0 = ax // 2
            gx0 = max(0, min(gx0, gw - 1))
            gx1 = min(gx0 + 1, gw - 1)
            fx = 0.5 if ax % 2 == 0 else 0.0
            v = (ir[gy0][gx0] * (1 - fx) * (1 - fy) +
                 ir[gy0][gx1] * fx * (1 - fy) +
                 ir[gy1][gx0] * (1 - fx) * fy +
                 ir[gy1][gx1] * fx * fy)
            full[y][x] = int(v)
    return full


def demosaic_color(px, wb_r=WB_R_DEFAULT, wb_b=WB_B_DEFAULT):
    """对裁切区 [OY,OY+OH) x [OX,OX+OW) 每个像素计算 R,G,B。
    用「像素级连续滑动窗口」插值：窗口以每个像素为心，采样点随像素连续变化。
    相位一律用绝对坐标(Y&3,X&3)，与传感器原点对齐（裁切不影响相位）。
    G 密集(50%)小窗(RG)；R/B 稀疏(12.5%)大窗(RB)。
    wb_r/wb_b: R/B 相对 G 的白平衡增益（纯分离时 =1.0）。
    """
    rgb = [[0] * OW for _ in range(OH)]

    # CH_ROW: 通道 -> {绝对行r: [绝对列c,...]}
    CH_ROW = {'R': {}, 'G': {}, 'B': {}}
    for r in range(4):
        for c in range(4):
            ch = PHASE[(r, c)]
            if ch in CHANS:
                CH_ROW[ch].setdefault(r, []).append(c)

    def interp(inty, intx, ch, R):
        """以绝对像素 (inty,intx) 为心，半径 R 内所有绝对相位==ch 的采样点
        做距离倒数加权插值，返回 0-1023。"""
        rows = CH_ROW[ch]
        sw = 0.0
        s = 0.0
        seen = set()
        for Y in range(max(OY, inty - R), min(OY + OH, inty + R + 1)):
            r = Y & 3
            if r not in rows:
                continue
            for c in rows[r]:
                # 该绝对行 r 上相位 col==c → 绝对列 X ≡ c (mod 4)
                X0 = (intx // 4) * 4 + c
                cands = {X0 - 4, X0, X0 + 4}
                for X in cands:
                    if X < OX or X >= OX + OW:
                        continue
                    if intx - R <= X <= intx + R and (Y, X) not in seen:
                        seen.add((Y, X))
                        d2 = (Y - inty) ** 2 + (X - intx) ** 2
                        w = 1.0 / (d2 + 1.0)
                        sw += w
                        s += w * px[Y][X]
        return s / sw if sw > 0 else 0

    RG, RB = 3, 8  # G 小窗锐利, R/B 大窗平滑
    for yy in range(OH):
        if yy % 100 == 0:
            print(f"  行 {yy}/{OH} ...", flush=True)
        ty = OY + yy
        for xx in range(OW):
            tx = OX + xx
            g = interp(ty, tx, 'G', RG)
            r = interp(ty, tx, 'R', RB) * wb_r
            b = interp(ty, tx, 'B', RB) * wb_b
            rgb[yy][xx] = (min(255, int(r * 255 // 1023)),
                           min(255, int(g * 255 // 1023)),
                           min(255, int(b * 255 // 1023)))
    return rgb, CH_ROW


def write_ppm_gray(path, gray):
    with open(path, 'wb') as f:
        f.write(b'P5\n%d %d\n255\n' % (OW, OH))
        for y in range(OH):
            f.write(bytes(min(255, int(gray[y][x] * 255 // 1023)) for x in range(OW)))


def normalize_rgb(rgb):
    """白点归一化：以裁切区 R,G,B 三通道整体的 p99.5 高值为参考白点，
    把 RGB 全部等比例拉伸，使该高值接近满亮度(255)。
    R/B/G 同比缩放 -> 保留色相/色比，只整体提亮（解决"偏暗"）。
    rgb: 0-255 的 (r,g,b) 三元组二维表，原地修改。"""
    vals = sorted(rgb[y][x][k] for y in range(OH) for x in range(OW) for k in range(3))
    p = vals[max(0, int(len(vals) * 0.995) - 1)]
    if p <= 0:
        return
    scale = 255.0 / p if p < 255 else 1.0
    if scale <= 1.0:
        return
    for y in range(OH):
        for x in range(OW):
            r, g, b = rgb[y][x]
            rgb[y][x] = (min(255, int(r * scale)),
                         min(255, int(g * scale)),
                         min(255, int(b * scale)))


def write_ppm_rgb(path, rgb):
    with open(path, 'wb') as f:
        f.write(b'P6\n%d %d\n255\n' % (OW, OH))
        for y in range(OH):
            row = bytearray()
            for x in range(OW):
                row += bytes(rgb[y][x])
            f.write(bytes(row))


def to_png(ppm, png):
    subprocess.run(['magick', ppm, png], check=True)


def main():
    # 用法: in.raw out_prefix [Rgain Bgain] [OW OH [CX CY]] [--norm]
    # 未指定 CX,CY 时自动检测该 raw 的屏幕中心(每图不同，逐图检测)。
    if len(sys.argv) < 3:
        raise SystemExit("用法: python3 demosaic_color.py in.raw out_prefix [Rgain Bgain] [OW OH [CX CY]] [--norm]")
    global NORMALIZE
    NORMALIZE = '--norm' in sys.argv
    args = [a for a in sys.argv[1:] if a != '--norm']
    inp, pref = args[0], args[1]
    wb_r = float(args[2]) if len(args) > 2 else WB_R_DEFAULT
    wb_b = float(args[3]) if len(args) > 3 else WB_B_DEFAULT
    global OW, OH, CX, CY, OX, OY
    if len(args) > 4:
        OW = int(args[4])
    if len(args) > 5:
        OH = int(args[5])
    px = read_raw(inp)
    if len(args) > 7:
        CX = int(args[6])
        CY = int(args[7])
        print(f"  手动屏幕中心=({CX},{CY})")
    else:
        CX, CY = auto_screen_center(px)
        print(f"  自动检测屏幕中心=({CX},{CY})")
    OX = CX - OW // 2
    OY = CY - OH // 2
    print(f"  裁切区 {OW}x{OH} @ ({OX},{OY})")
    print("IR 分离 ...")
    ir = extract_ir(px)
    write_ppm_gray(pref + '_ir.ppm', ir)
    to_png(pref + '_ir.ppm', pref + '_ir.png')
    print(f"彩色 demosaic (纯分离 WB R={wb_r}, B={wb_b}) ...")
    rgb, _ = demosaic_color(px, wb_r, wb_b)
    if NORMALIZE:
        print("亮度归一化（白点拉伸，解决偏暗）...")
        normalize_rgb(rgb)
    write_ppm_rgb(pref + '_color.ppm', rgb)
    to_png(pref + '_color.ppm', pref + '_color.png')
    print("完成:", pref + '_ir.png', pref + '_color.png')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
交互式颜色/色调调整工具（OV5678 RGB-IR 彩色图）
================================================
从 raw 生成彩色图后，进入交互式命令行实时调整色调，每改一次就重新生成 PNG，
你在图像查看器里刷新即可看到新效果。满意后保存参数，退出时打印整套参数。

用法：
  python3 color_tune.py in.raw out_prefix [OW OH] [初始Rgain 初始Bgain]

  in.raw      : 输入 raw (2592x1944)
  out_prefix  : 输出前辍（生成 <out_prefix>_color.png 、<out_prefix>_params.txt）
  OW OH       : 裁切尺寸（默认 1200x900，基于自动检测的屏幕中心）
  初始Rgain/Bgain : 初始白平衡增益（默认 1.0）

交互命令（输入后回车，自动重生成 PNG，请到查看器刷新查看）：
  r <val>     R 通道增益（>1 偏红，<1 偏青）
  g <val>     G 通道增益（>1 偏绿，<1 偏品红）
  b <val>     B 通道增益（>1 偏蓝，<1 偏黄）
  hue <deg>   色相旋转角度 -180 ~ 180（正值顺时针）
  gam <val>   伽马校正（1.0=线性；<1 提亮暗部；>1 压暗）
  save        保存当前全套参数到 <out_prefix>_params.txt
  print       打印当前参数
  q           退出（退出前会自动保存当前参数）
"""
import sys
import demosaic_color as dc


def rgb_to_hsv(r, g, b):
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    mx = max(r, g, b); mn = min(r, g, b); d = mx - mn
    h = 0.0
    if d > 1e-9:
        if mx == r:
            h = 60 * (((g - b) / d) % 6)
        elif mx == g:
            h = 60 * ((b - r) / d + 2)
        else:
            h = 60 * ((r - g) / d + 4)
    s = 0.0 if mx == 0 else d / mx
    return h, s, mx


def hsv_to_rgb(h, s, v):
    h = h % 360
    c = v * s
    x = c * (1 - abs(((h / 60) % 2) - 1))
    m = v - c
    if h < 60:   r, g, b = c, x, 0
    elif h < 120: r, g, b = x, c, 0
    elif h < 180: r, g, b = 0, c, x
    elif h < 240: r, g, b = 0, x, c
    elif h < 300: r, g, b = x, 0, c
    else:        r, g, b = c, 0, x
    return int((r + m) * 255), int((g + m) * 255), int((b + m) * 255)


def tune(rgb, rg, gg, bg, hue, gamma):
    """在纯分离 RGB(0-255) 上依次应用: 增益 -> 伽马 -> 色相旋转。"""
    H = len(rgb); W = len(rgb[0])
    out = [[(0, 0, 0)] * W for _ in range(H)]
    inv = 1.0 / gamma if gamma != 0 else 1.0
    for y in range(H):
        row = rgb[y]
        for x in range(W):
            r, g, b = row[x]
            r2 = r * rg; g2 = g * gg; b2 = b * bg
            # 默认不做伽马（gamma==1 时略过，保持速度）
            if gamma != 1.0:
                r2 = 255.0 * ((r2 / 255.0) ** inv)
                g2 = 255.0 * ((g2 / 255.0) ** inv)
                b2 = 255.0 * ((b2 / 255.0) ** inv)
            if hue:
                h, s, v = rgb_to_hsv(r2, g2, b2)
                r2, g2, b2 = hsv_to_rgb(h + hue, s, v)
            out[y][x] = (min(255, max(0, int(r2))),
                         min(255, max(0, int(g2))),
                         min(255, max(0, int(b2))))
    return out


def main():
    if len(sys.argv) < 3:
        raise SystemExit("用法: python3 color_tune.py in.raw out_prefix [OW OH] [Rgain Bgain]\n"
                         "  (可再传 OW OH 裁切尺寸与初始 R/B 增益)")
    inp, pref = sys.argv[1], sys.argv[2]
    OW, OH = 1200, 900
    rg = gg = bg = 1.0
    hue = 0.0
    gamma = 1.0
    # 解析可选参数
    nums = []
    for a in sys.argv[3:]:
        try:
            nums.append(float(a))
        except ValueError:
            pass
    if len(nums) >= 2:
        OW, OH = int(nums[0]), int(nums[1])
    if len(nums) >= 4:
        rg, bg = nums[2], nums[3]

    # 读 raw + 检测屏幕中心 + 裁切
    dc.OW, dc.OH = OW, OH
    px = dc.read_raw(inp)
    cx, cy = dc.auto_screen_center(px)
    dc.CX, dc.CY = cx, cy
    dc.OX, dc.OY = cx - OW // 2, cy - OH // 2
    print(f"屏幕中心=({cx},{cy}) 裁切 {OW}x{OH} @ ({dc.OX},{dc.OY})")

    # 用纯分离(wb=1,1)生成基础 RGB，后续所有调整在后处理层做
    base_rgb, _ = dc.demosaic_color(px, 1.0, 1.0)
    print("基础纯分离 RGB 已生成，进入交互调整。输入 help 查看命令。")

    def regenerate():
        tuned = tune(base_rgb, rg, gg, bg, hue, gamma)
        dc.write_ppm_rgb(pref + '_color.ppm', tuned)
        dc.to_png(pref + '_color.ppm', pref + '_color.png')
        print(f"  已更新 {pref}_color.png   (R={rg:.3f} G={gg:.3f} B={bg:.3f} hue={hue:.1f}° gam={gamma:.2f})")

    def save_params():
        with open(pref + '_params.txt', 'w') as f:
            f.write(f"r_gain={rg:.4f}\n")
            f.write(f"g_gain={gg:.4f}\n")
            f.write(f"b_gain={bg:.4f}\n")
            f.write(f"hue={hue:.2f}\n")
            f.write(f"gamma={gamma:.4f}\n")
        print(f"  参数已保存到 {pref}_params.txt")

    regenerate()
    while True:
        try:
            line = input("tune> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n退出前保存...")
            save_params()
            print(f"最终参数: R={rg:.3f}, G={gg:.3f}, B={bg:.3f}, hue={hue:.1f}°, gamma={gamma:.2f}")
            break
        if not line:
            continue
        parts = line.split()
        cmd, val = parts[0], (float(parts[1]) if len(parts) > 1 else None)
        if cmd == 'q':
            save_params()
            print(f"最终参数: R={rg:.3f}, G={gg:.3f}, B={bg:.3f}, hue={hue:.1f}°, gamma={gamma:.2f}")
            break
        elif cmd == 'save':
            save_params()
        elif cmd == 'print' or cmd == 'p':
            print(f"R={rg:.3f}, G={gg:.3f}, B={bg:.3f}, hue={hue:.1f}°, gamma={gamma:.2f}")
            continue
        elif cmd == 'help':
            print("命令: r <v> | g <v> | b <v> | hue <deg> | gam <v> | save | print | q")
            continue
        elif val is None:
            print("需要数值参数")
            continue
        elif cmd == 'r':
            rg = val
        elif cmd == 'g':
            gg = val
        elif cmd == 'b':
            bg = val
        elif cmd == 'hue':
            hue = val % 360 if val >= 0 else (val % 360)
        elif cmd == 'gam':
            gamma = val
        else:
            print(f"未知命令: {cmd} (输入 help)")
            continue
        regenerate()


if __name__ == '__main__':
    main()

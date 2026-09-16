#!/usr/bin/env python3
"""用 C 的 NN 快速模式生成实时预览图 + 量化 NN 与精确 IDW 差异（质量评估用）。

用法:
  python3 gen_preview_nn.py in.raw out_prefix [OW OH] [Rgain Bgain]

生成:
  out_preview.png    NN 快速模式（实时预览视觉）
  out_idw.png        精确 IDW 模式（最终导出参照）
  （另打印 NN vs IDW 的每通道平均绝对差，供判断 NN 质量是否可接受）
"""
import sys, time, ctypes, subprocess
import demosaic_color as dc

lib = ctypes.CDLL('./demosaic_fast.so')
lib.read_raw.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                         ctypes.POINTER(ctypes.c_uint16), ctypes.c_int, ctypes.c_int]
lib.demosaic_and_ir.argtypes = [ctypes.POINTER(ctypes.c_uint16),
                                ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int,
                                ctypes.c_double, ctypes.c_double,
                                ctypes.POINTER(ctypes.c_uint8),
                                ctypes.POINTER(ctypes.c_uint8)]
lib.demosaic_nn.argtypes = [ctypes.POINTER(ctypes.c_uint16),
                            ctypes.c_int, ctypes.c_int,
                            ctypes.c_int, ctypes.c_int,
                            ctypes.c_int, ctypes.c_int,
                            ctypes.c_double, ctypes.c_double,
                            ctypes.POINTER(ctypes.c_uint8)]

W, H = dc.W, dc.H
inp, pref = sys.argv[1], sys.argv[2]
OW = int(sys.argv[3]) if len(sys.argv) > 3 else 1200
OH = int(sys.argv[4]) if len(sys.argv) > 4 else 900
wb_r = float(sys.argv[5]) if len(sys.argv) > 5 else 1.36
wb_b = float(sys.argv[6]) if len(sys.argv) > 6 else 1.36

# C 端 raw
data = open(inp, 'rb').read()
px = (ctypes.c_uint16 * (W * H))()
lib.read_raw(data, len(data), px, W, H)
# 屏幕中心（用 Python 检测以便复用逻辑）
px_py = dc.read_raw(inp)
CX, CY = dc.auto_screen_center(px_py)
OX, OY = CX - OW // 2, CY - OH // 2
print(f"屏幕中心=({CX},{CY}) 裁切区 {OW}x{OH}  WB r={wb_r:.3f} b={wb_b:.3f}")

rgb_buf = (ctypes.c_uint8 * (OW * OH * 3))()
ir_buf = (ctypes.c_uint8 * (OW * OH))()

# NN 快速
t0 = time.time()
lib.demosaic_nn(px, W, H, OX, OY, OW, OH, wb_r, wb_b, rgb_buf)
nn = bytes(rgb_buf)
t_nn = time.time() - t0
print(f"NN 预览: {t_nn*1000:.1f}ms  -> 约 {1.0/t_nn:.1f} fps")

# IDW 精确
t0 = time.time()
lib.demosaic_and_ir(px, W, H, OX, OY, OW, OH, wb_r, wb_b, rgb_buf, ir_buf)
idw = bytes(rgb_buf)
t_idw = time.time() - t0
print(f"IDW 精确: {t_idw*1000:.1f}ms")

# 写 PPM
def write_ppm_rgb(path, rgb):
    with open(path, 'wb') as f:
        f.write(b'P6\n%d %d\n255\n' % (OW, OH))
        f.write(rgb)
write_ppm_rgb(pref + '_preview.ppm', nn)
write_ppm_rgb(pref + '_idw.ppm', idw)

# PNG
subprocess.run(['magick', pref + '_preview.ppm', pref + '_preview.png'], check=True)
subprocess.run(['magick', pref + '_idw.ppm', pref + '_idw.png'], check=True)

# NN vs IDW 逐通道平均绝对差（0-255 域）
n = OW * OH
diff = [0, 0, 0]
for i in range(OW * OH):
    for c in range(3):
        diff[c] += abs(nn[i * 3 + c] - idw[i * 3 + c])
print("\nNN vs IDW 每通道平均绝对差 (0-255 域):")
for name, d in zip('RGB', diff):
    print(f"  {name}: {d / n:.2f}")
print("\n生成:", pref + '_preview.png', '(', pref + '_idw.png', ')')

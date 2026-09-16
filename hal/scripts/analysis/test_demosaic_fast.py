#!/usr/bin/env python3
"""测试 C demosaic (demosaic_fast.so) 与 Python 版 (demosaic_color) 输出一致性 + 计时。

用法:
  python3 test_demosaic_fast.py in.raw [OW OH]
默认裁切区 1200x900（全屏中心）。一致性对比在小窗(如96x72)进行以让 Python 版可跑完。
"""
import sys, time, ctypes
import demosaic_color as dc

# ---- 加载 C 库 ----
lib = ctypes.CDLL('./demosaic_fast.so')

# read_raw(const uint8_t*, size_t, uint16_t*, int W, int H)
lib.read_raw.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                         ctypes.POINTER(ctypes.c_uint16), ctypes.c_int, ctypes.c_int]
# demosaic_and_ir(px, W,H, OX,OY,OW,OH, wb_r, wb_b, rgb, ir)
lib.demosaic_and_ir.argtypes = [ctypes.POINTER(ctypes.c_uint16),
                                ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int,
                                ctypes.c_double, ctypes.c_double,
                                ctypes.POINTER(ctypes.c_uint8),
                                ctypes.POINTER(ctypes.c_uint8)]
# demosaic_nn(px, W,H, OX,OY,OW,OH, wb_r, wb_b, rgb)
lib.demosaic_nn.argtypes = [ctypes.POINTER(ctypes.c_uint16),
                            ctypes.c_int, ctypes.c_int,
                            ctypes.c_int, ctypes.c_int,
                            ctypes.c_int, ctypes.c_int,
                            ctypes.c_double, ctypes.c_double,
                            ctypes.POINTER(ctypes.c_uint8)]

def c_read_raw(path, W, H):
    data = open(path, 'rb').read()
    px = (ctypes.c_uint16 * (W * H))()
    lib.read_raw(data, len(data), px, W, H)
    return px

def c_demosaic(px, W, H, OX, OY, OW, OH, wb_r, wb_b):
    rgb = (ctypes.c_uint8 * (OW * OH * 3))()
    ir = (ctypes.c_uint8 * (OW * OH))()
    lib.demosaic_and_ir(px, W, H, OX, OY, OW, OH, wb_r, wb_b, rgb, ir)
    return bytes(rgb), bytes(ir)

def c_demosaic_nn(px, W, H, OX, OY, OW, OH, wb_r, wb_b):
    rgb = (ctypes.c_uint8 * (OW * OH * 3))()
    lib.demosaic_nn(px, W, H, OX, OY, OW, OH, wb_r, wb_b, rgb)
    return bytes(rgb)

# ---- 设置全局参数 ----
W, H = dc.W, dc.H
inp = sys.argv[1]
OW = int(sys.argv[2]) if len(sys.argv) > 2 else 1200
OH = int(sys.argv[3]) if len(sys.argv) > 3 else 900
wb_r, wb_b = 1.0, 1.0  # 一致性对比用纯分离

# 读 raw 一次
data = open(inp, 'rb').read()
px_py = dc.read_raw(inp)          # Python 版 (list[list])
px_c = c_read_raw(inp, W, H)      # C 版 (uint16*)

# 检测屏幕中心（复用 Python 版逻辑）
CX, CY = dc.auto_screen_center(px_py)
print(f"屏幕中心=({CX},{CY}) 裁切区 {OW}x{OH}")

dc.OW, dc.OH = OW, OH
dc.CX, dc.CY = CX, CY
dc.OX = CX - OW // 2
dc.OY = CY - OH // 2
OX, OY = dc.OX, dc.OY

# ---- A. 一致性对比（用小窗，Python 版才能跑完）----
cw, ch = 96, 72
cOX = OX + (OW - cw) // 2
cOY = OY + (OH - ch) // 2
print(f"\n[A] 一致性对比窗口 {cw}x{ch} @({cOX},{cOY}) ...")

# Python 参考
t0 = time.time()
rgb_py, _ = dc.demosaic_color(px_py, wb_r, wb_b)  # 但它在 dc 全裁切区算...
# 我们只要窗口部分 —— 为公平用 C 在全裁切区做，Python 全裁切区太慢。
# 所以这里让 Python 版也只在窗口裁切区算：
dc.OW, dc.OH = cw, ch
dc.CX, dc.CY = cOX + cw // 2, cOY + ch // 2
dc.OX = cOX
dc.OY = cOY
t0 = time.time()
rgb_py, _ = dc.demosaic_color(px_py, wb_r, wb_b)
t_py = time.time() - t0
# Python IR
ir_py = dc.extract_ir(px_py)

# C 在窗口
t0 = time.time()
rgb_c, ir_c = c_demosaic(px_c, W, H, cOX, cOY, cw, ch, wb_r, wb_b)
t_c_once = time.time() - t0

def flat(px_l, W, H):
    out = bytearray()
    for y in range(H):
        for x in range(W):
            out += bytes(px_l[y][x])
    return bytes(out)

rgb_py_b = flat(rgb_py, cw, ch)
# 一致率（逐字节）
tot = len(rgb_py_b)
match = sum(1 for a, b in zip(rgb_py_b, rgb_c) if a == b)
print(f"  彩色 channel 一致率: {match}/{tot} = {match*100.0/tot:.3f}%")
# RGB 每通道一致率
chan = [[0, 0], [0, 0], [0, 0]]
for i in range(tot):
    ch = i % 3
    chan[ch][0] += 1
    if rgb_py_b[i] == rgb_c[i]:
        chan[ch][1] += 1
for name, (t, m) in zip('RGB', chan):
    print(f"     {name}: {m}/{t} = {m*100.0/t:.2f}%")

# IR 一致率
tot_i = len(ir_py) * 0
ir_py_b = bytes(int(ir_py[y][x] * 255 // 1023) for y in range(ch) for x in range(cw))
tot_i = len(ir_py_b)
m_i = sum(1 for a, b in zip(ir_py_b, ir_c) if a == b)
print(f"  IR 一致率: {m_i}/{tot_i} = {m_i*100.0/tot_i:.3f}%")

# ---- B. 全尺寸性能计时（C，多次）----
print(f"\n[B] 全裁切区 {OW}x{OH} C 性能（WB纯分离）:")
# 预热一次
c_demosaic(px_c, W, H, OX, OY, OW, OH, wb_r, wb_b)
N = 5
t0 = time.time()
for _ in range(N):
    c_demosaic(px_c, W, H, OX, OY, OW, OH, wb_r, wb_b)
dt = (time.time() - t0) / N
print(f"  [精确 IDW] 平均 {dt*1000:.1f} ms/帧 -> 约 {1.0/dt:.1f} fps")

# NN 快速模式
c_demosaic_nn(px_c, W, H, OX, OY, OW, OH, wb_r, wb_b)  # 预热
t0 = time.time()
for _ in range(N):
    c_demosaic_nn(px_c, W, H, OX, OY, OW, OH, wb_r, wb_b)
dn = (time.time() - t0) / N
print(f"  [最近邻 NN] 平均 {dn*1000:.1f} ms/帧 -> 约 {1.0/dn:.1f} fps")
print(f"  [参考] Python 版小窗 {cw}x{ch} 耗时 {t_py:.1f}s")

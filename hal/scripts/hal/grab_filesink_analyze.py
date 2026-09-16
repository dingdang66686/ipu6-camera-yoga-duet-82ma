#!/usr/bin/env python3
"""用 icamerasrc + filesink 捕获 NV12 视频流，正常关闭 flush 后分析颜色。
避开 appsink 的 executePG 问题，使用 filesink（与 fakesink 同样健康的帧节奏）。
"""
import sys, time
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import numpy as np

Gst.init(None)

dev = sys.argv[1] if len(sys.argv) > 1 else 'ov5675-uf'
out = sys.argv[2] if len(sys.argv) > 2 else '/tmp/frame.nv12'
seconds = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0

width, height = 1280, 720
caps = f'video/x-raw,format=NV12,width={width},height={height}'
launch = f'icamerasrc device-name={dev} ! {caps} ! filesink location={out}'
pipe = Gst.parse_launch(launch)

pipe.set_state(Gst.State.PLAYING)

# 运行 seconds 秒后优雅关闭（触发 filesink flush）
start = time.time()
while time.time() - start < seconds:
    GLib.MainContext.default().iteration(False)
    time.sleep(0.01)

pipe.set_state(Gst.State.NULL)

# 读取文件分析
import os
size = os.path.getsize(out) if os.path.exists(out) else 0
expected = width * height * 3 // 2
print(f"FILE_SIZE: {size} (expected each frame {expected})")
frames = size // expected
print(f"FRAMES: {frames}")
if frames == 0:
    print("NO_FRAMES")
    sys.exit(1)

with open(out, 'rb') as f:
    data = f.read()

# 分析最后一帧
nv12 = np.frombuffer(data[-expected:], dtype=np.uint8).reshape(height*3//2, width)
raw = nv12.copy()
Y = raw[:height, :].astype(np.float32)
UV = raw[height:, :].reshape(height//2, width)
U = UV[::2, ::2].astype(np.float32)
V = UV[::2, 1::2].astype(np.float32)

# BT.601 转 RGB
b = 1.164*(Y-16)+2.018*(U-128)
r = 1.164*(Y-16)+1.596*(V-128)
g = 1.164*(Y-16)-0.391*(U-128)-0.813*(V-128)

print(f"Y mean={Y.mean():.1f} min={Y.min()} max={Y.max()}")
print(f"U mean={U.mean():.1f} min={U.min()} max={U.max()}")
print(f"V mean={V.mean():.1f} min={V.min()} max={V.max()}")
print(f"R mean={r.mean():.1f}  G mean={g.mean():.1f}  B mean={b.mean():.1f}")

# 检查色彩饱和度（判断是否灰度/偏色）
Rc, Gc, Bc = r.mean(), g.mean(), b.mean()
sat = 0.5*((Rc-Gc).__abs__() + (Gc-Bc).__abs__() + (Rc-Bc).__abs__())
print(f"COLOR_SATURATION(deltaRGB): {sat:.1f}")
if sat < 5:
    print("VERDICT: 疑似灰度/无色画面 (颜色缺失!)")
elif abs(Rc-Bc) > 40 and Gc < min(Rc,Bc):
    print(f"VERDICT: 疑似偏品红/红 (R={Rc:.0f} G={Gc:.0f} B={Bc:.0f})")
elif abs(Gc-Bc) > 40 and Rc < min(Gc,Bc):
    print(f"VERDICT: 疑似偏青/绿 (R={Rc:.0f} G={Gc:.0f} B={Bc:.0f})")
else:
    print(f"VERDICT: 有彩色且分布较均衡 (R={Rc:.0f} G={Gc:.0f} B={Bc:.0f})")

# 保存一帧为 PGM 供 ffmpeg/ImageMagick 进一步分析
with open('/tmp/last_Y.pgm', 'wb') as f:
    f.write(b'P5\n%d %d\n255\n' % (width, height))
    f.write(Y.astype(np.uint8).tobytes())
print("saved /tmp/last_Y.pgm")

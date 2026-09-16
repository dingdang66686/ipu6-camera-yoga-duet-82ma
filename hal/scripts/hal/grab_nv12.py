#!/usr/bin/env python3
"""用 icamerasrc + filesink 捕获指定分辨率 NV12 视频流，分析帧数和颜色。
用法: grab_nv12.py [device] [width] [height] [seconds] [outfile]
"""
import sys, time, os
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import numpy as np

Gst.init(None)

dev = sys.argv[1] if len(sys.argv) > 1 else 'ov5675-uf'
width = int(sys.argv[2]) if len(sys.argv) > 2 else 2560
height = int(sys.argv[3]) if len(sys.argv) > 3 else 1920
seconds = float(sys.argv[4]) if len(sys.argv) > 4 else 4.0
out = sys.argv[5] if len(sys.argv) > 5 else '/tmp/fullres.nv12'

caps = f'video/x-raw,format=NV12,width={width},height={height}'
launch = f'icamerasrc device-name={dev} ! {caps} ! filesink location={out}'
print(f'LAUNCH: {launch}')
pipe = Gst.parse_launch(launch)
pipe.set_state(Gst.State.PLAYING)

start = time.time()
err = None
bus = pipe.get_bus()
while time.time() - start < seconds:
    GLib.MainContext.default().iteration(False)
    time.sleep(0.005)
    msg = bus.timed_pop_filtered(0, Gst.MessageType.ERROR | Gst.MessageType.EOS)
    if msg and msg.type == Gst.MessageType.ERROR:
        err = msg.parse_error()
        break
    if msg and msg.type == Gst.MessageType.EOS:
        break

pipe.set_state(Gst.State.NULL)

if err:
    print(f"GST_ERROR: {err[1]}")
    sys.exit(1)

size = os.path.getsize(out) if os.path.exists(out) else 0
expected = width * height * 3 // 2
if expected > 0:
    frames = size // expected
else:
    frames = 0
print(f"FILE_SIZE: {size} (expected/frame {expected})")
print(f"FRAMES: {frames}")
if frames == 0:
    print("NO_FRAMES")
    sys.exit(1)

with open(out, 'rb') as f:
    data = f.read()
nv12 = np.frombuffer(data[-expected:], dtype=np.uint8).reshape(height*3//2, width)
Y = nv12[:height, :].astype(np.float32)
UVplane = nv12[height:, :]  # shape (height/2, width), U 在偶列 V 在奇列
U = UVplane[:, 0::2].astype(np.float32)  # (height/2, width/2)
V = UVplane[:, 1::2].astype(np.float32)
b = 1.164*(Y-16)+2.018*(U-128)
r = 1.164*(Y-16)+1.596*(V-128)
g = 1.164*(Y-16)-0.391*(U-128)-0.813*(V-128)
print(f"Y mean={Y.mean():.1f} min={Y.min()} max={Y.max()}")
print(f"U mean={U.mean():.1f}  V mean={V.mean():.1f}")
print(f"R mean={r.mean():.1f}  G mean={g.mean():.1f}  B mean={b.mean():.1f}")
# 亮区(取最亮 5%)的色度，判断灰平衡
thr = np.percentile(Y, 95)
mask = Y > thr
u_hi = U[mask[::2,::2]].mean() if mask.any() else float('nan')
v_hi = V[mask[::2,::2]].mean() if mask.any() else float('nan')
print(f"高亮区(>P95) 像素数={mask.sum()}  U={u_hi:.1f} V={v_hi:.1f} (中性应≈128)")
sat = 0.5*(abs(r.mean()-g.mean())+abs(g.mean()-b.mean())+abs(r.mean()-b.mean()))
print(f"COLOR_SATURATION: {sat:.1f}")
# 存 PGM 供量化
with open('/tmp/fullres_Y.pgm','wb') as f:
    f.write(b'P5\n%d %d\n255\n' % (width,height)); f.write(Y.astype(np.uint8).tobytes())
print("DONE")

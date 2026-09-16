#!/usr/bin/env python3
"""用 icamerasrc + appsink 抓取指定帧数，保存 NV12 并量化分析颜色。"""
import sys, time
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
from gi.repository import Gst, GLib, GstApp
import numpy as np

Gst.init(None)

dev = sys.argv[1] if len(sys.argv) > 1 else '4'
out = sys.argv[2] if len(sys.argv) > 2 else '/tmp/frame.raw'
nframes = int(sys.argv[3]) if len(sys.argv) > 3 else 3

caps = 'video/x-raw,format=NV12,width=1280,height=720'
launch = f'icamerasrc device-name={dev} ! {caps} ! appsink name=sink max-buffers=1 drop=true'
pipe = Gst.parse_launch(launch)
sink = pipe.get_by_name('sink')

saved = []
def collect(sample):
    b = sample.get_buffer()
    ok, data = b.map(Gst.MapFlags.READ)
    if ok:
        saved.append(bytes(data))
        b.unmap(b)
    return Gst.FlowReturn.OK

sink.set_property('emit-signals', True)
sink.connect('new-sample', collect)

pipe.set_state(Gst.State.PLAYING)

# 最多等 ~15 秒抓 nframes 帧
start = time.time()
while len(saved) < nframes and time.time() - start < 15:
    time.sleep(0.1)
    GLib.MainContext.default().iteration(False)

pipe.set_state(Gst.State.NULL)

if not saved:
    print("NO_FRAMES")
    sys.exit(1)

print(f"GOT {len(saved)} frames, each {len(saved[0])} bytes")

for i, data in enumerate(saved[:nframes]):
    with open(f"{out}.{i}.raw", 'wb') as f:
        f.write(data)
    nv12 = np.frombuffer(data, dtype=np.uint8).reshape(720*3//2, 1280)
    Y = nv12[:720, :].astype(np.float32)
    UV = nv12[720:, :].reshape(360, 1280)
    U = UV[::2, ::2].astype(np.float32)
    V = UV[::2, 1::2].astype(np.float32)
    b = 1.164*(Y-16)+2.018*(U-128)
    r = 1.164*(Y-16)+1.596*(V-128)
    g = 1.164*(Y-16)-0.391*(U-128)-0.813*(V-128)
    print(f"frame{i}: Ymean={Y.mean():.1f} R={r.mean():.1f} G={g.mean():.1f} B={b.mean():.1f} "
          f"U={U.mean():.1f} V={V.mean():.1f}")

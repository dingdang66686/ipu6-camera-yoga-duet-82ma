#!/usr/bin/env python3
"""icamerasrc 抓帧脚本（回调版）"""
import sys, time, threading
import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstApp', '1.0')
from gi.repository import Gst, GLib, GstApp
import numpy as np

Gst.init(None)
dev = sys.argv[1] if len(sys.argv) > 1 else '4'
outprefix = sys.argv[2] if len(sys.argv) > 2 else '/tmp/frame'
total = int(sys.argv[3]) if len(sys.argv) > 3 else 3

pipe = Gst.parse_launch(
    f'icamerasrc device-name={dev} ! '
    'video/x-raw,format=NV12,width=1280,height=720 ! '
    'appsink name=sink max-buffers=2 drop=true'
)
sink = pipe.get_by_name('sink')
frames = []
loop = GLib.MainLoop()

def pull_cb():
    # 非阻塞拉取样本
    sample = sink.try_pull_sample(0)
    if sample:
        b = sample.get_buffer()
        ok, data = b.map(Gst.MapFlags.READ)
        if ok:
            frames.append(bytes(data))
            b.unmap(b)
            if len(frames) >= total:
                loop.quit()
                return False
    return True

GLib.timeout_add(5, pull_cb)  # 每 5ms 轮询
# 超时保护: 25s 后退出
def timeout_cb():
    loop.quit()
    return False
GLib.timeout_add_seconds(25, timeout_cb)

pipe.set_state(Gst.State.PLAYING)
try:
    loop.run()
except Exception as e:
    print("EXC", e)
pipe.set_state(Gst.State.NULL)

if not frames:
    print("NO_FRAMES")
else:
    print(f"GOT {len(frames)} frames, each {len(frames[0])} bytes")
    for i, data in enumerate(frames):
        with open(f"{outprefix}.{i}.raw", 'wb') as f:
            f.write(data)
        nv12 = np.frombuffer(data, dtype=np.uint8).reshape(720*3//2, 1280)
        Y = nv12[:720, :].astype(np.float32)
        UV = nv12[720:, :].reshape(360, 1280)
        U = UV[::2, ::2].astype(np.float32)
        V = UV[::2, 1::2].astype(np.float32)
        b = 1.164*(Y-16)+2.018*(U-128)
        r = 1.164*(Y-16)+1.596*(V-128)
        g = 1.164*(Y-16)-0.391*(U-128)-0.813*(V-128)
        print(f"frame{i}: Y={Y.mean():.1f} R={r.mean():.1f} G={g.mean():.1f} B={b.mean():.1f} U={U.mean():.1f} V={V.mean():.1f}")

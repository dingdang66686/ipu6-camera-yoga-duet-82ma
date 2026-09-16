#!/usr/bin/env python3
"""
pipewiresink Camera-node 可行性验证脚本 (spike)

目的：确认 pipewiresink 能通过 stream-properties 把一个源
暴露为 PipeWire 的 media.class=Video/Source + media.role=Camera node，
从而被 xdg-desktop-portal / aperture (GNOME Snapshot) 识别为相机。

用 videotestsrc 作为测试源（不碰 icamerasrc / CamHAL），验证接入管道本身。
"""
import sys
import gi

gi.require_version("Gst", "1.0")
from gi.repository import Gst, GLib

Gst.init(None)

# ---- 管道 ----
# videotestsrc -> capsfilter(NV12) -> pipewiresink(stream-properties=...)
pipe = Gst.Pipeline.new("pipewire-cam-verify")

src = Gst.ElementFactory.make("videotestsrc", "src")
src.set_property("pattern", 0)  # SMPTE 彩条，便于量化验证
src.set_property("num-buffers", -1)  # 持续运行

caps = Gst.Caps.from_string(
    "video/x-raw,format=NV12,width=640,height=480,framerate=30/1"
)
capfilter = Gst.ElementFactory.make("capsfilter", "caps")
capfilter.set_property("caps", caps)

sink = Gst.ElementFactory.make("pipewiresink", "sink")

# ---- 关键：stream-properties 用 Gst.Structure 程序化设置 ----
# 这些 key 会被原样复制进 pw_stream_new 的 properties，
# 进而被 PipeWire 提升为 node properties，驱动 WirePlumber 分类。
sp = Gst.Structure.new_empty("applications/x-pipewire-stream")
sp.set_value("media.class", "Video/Source")
sp.set_value("media.role", "Camera")
sp.set_value("node.name", "pw_verify_camera")
sp.set_value("node.description", "PipeWire Verify Camera")
sp.set_value("media.type", "Video")
sp.set_value("media.category", "Source")
sink.set_property("stream-properties", sp)

# 默认 stream-properties 可能带 media.class=Stream 等，这里显式覆盖后应生效

pipe.add(src)
pipe.add(capfilter)
pipe.add(sink)
src.link(capfilter)
capfilter.link(sink)

bus = pipe.get_bus()
bus.add_signal_watch()
msgs = {"errors": []}


def on_error(bus_, msg):
    err, dbg = msg.parse_error()
    msgs["errors"].append(f"ERROR: {err.message} | {dbg}")
    GLib.MainLoop.quit(loop)


bus.connect("message::error", on_error)


def on_eos(bus_, msg):
    print("EOS")
    GLib.MainLoop.quit(loop)


bus.connect("message::eos", on_eos)

loop = GLib.MainLoop()

# 运行一段时间后退出（后台由 icam-ctrl-daemon 长期运行，这里只验证）
def _on_timeout():
    GLib.MainLoop.quit(loop)
    return False  # 一次性

GLib.timeout_add_seconds(25, _on_timeout)  # 给足时间让 wpctl/portal 观察

ret = pipe.set_state(Gst.State.PLAYING)
if ret == Gst.StateChangeReturn.FAILURE:
    print("FATAL: 无法进入 PLAYING")
    sys.exit(1)

print("管道已 PLAYING，运行 25 秒（请在另一终端观察 wpctl status）")
loop.run()

pipe.set_state(Gst.State.NULL)

if msgs["errors"]:
    print("\n=== 运行期错误 ===")
    for e in msgs["errors"]:
        print(" ", e)
    sys.exit(1)

print("\n=== 完成：管道稳定运行无错误 ===")
print("在另一终端执行：wpctl status | grep -A2 -i camera")

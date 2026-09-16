#!/usr/bin/env python3
"""
OV5678 RGB-IR 实时白平衡调谐工具（浏览器版）
=============================================
直接控制 GPU debayer 的实时白平衡覆盖。

原理：
  debayer_cpu.cpp 的 pushGpuDebayerParams() 每帧读取 RGBIR_WB_CTRL 指向的
  文本文件（行 `R <val>` / `B <val>`）。本工具：
    1) 后台持续跑 `cam ... --file=/tmp/wb_prev#-f.ppm`（导出 RGBIR_WB_CTRL）
    2) 读取最新一帧 -> magick 转 JPEG -> 浏览器 MJPEG 实时预览
    3) 浏览器滑块 R/B -> /set 把值写进 /tmp/rgbir_wb -> debayer 下一帧即生效
       （无需重启相机/管线）

用法：
  python3 wb_tune.py [端口]
  默认端口 8767。浏览器打开 http://localhost:8767/
  拖动 R/B 滑块即可实时看到画面白平衡变化；点「重置」恢复 1.0。

（可选）想把这套滑块也作用于 PipeWire/GNOME Snapshot：
  systemctl --user import-environment RGBIR_WB_CTRL
  systemctl --user restart wireplumber

依赖：系统已安装 ImageMagick（magick）用于 PPM->JPEG；numpy 用于读 PPM。
"""
import os
import sys
import json
import glob
import time
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

CTRL_FILE = '/tmp/rgbir_wb'     # debayer 每帧读取的控制文件
PREV_GLOB = '/tmp/wb_prev*-f.ppm'
CAM = '/usr/local/bin/cam'
PORT = 8767

cur_r = 1.0
cur_b = 1.0
lock = threading.Lock()
last_frame = None   # (ppm_bytes) latest captured frame
frame_fail = False


def run_cam():
    """后台持续抓帧，写入 /tmp/wb_prev#-f.ppm；进程内导出 RGBIR_WB_CTRL。"""
    env = dict(os.environ)
    env['RGBIR_WB_CTRL'] = CTRL_FILE
    # 保持默认 AWB 打开；capture 一个很大数让它一直跑，timeout 兜底
    cmd = [CAM, '-c', '1', '--capture=100000',
           '-s', 'role=viewfinder', '--file=/tmp/wb_prev#-f.ppm']
    try:
        subprocess.run(cmd, env=env, check=False)
    except Exception:
        pass


def read_latest_ppm(retries=4):
    """读取最新一帧 PPM（P6 1288x972 RGGB RGB888），返回 bytes 或 None。
    30fps 下文件名被反复重写，可能撞上写入中途，故做几次短重试。"""
    fs = glob.glob(PREV_GLOB)
    if not fs:
        return None
    # cam 用数字递增命名，取编号最大（最新）的帧
    def sortkey(p):
        try:
            return int(p.split('-')[-2])
        except Exception:
            return 0
    p = max(fs, key=sortkey)
    for _ in range(retries):
        try:
            with open(p, 'rb') as f:
                data = f.read()
            rgb = _parse_ppm(data)
            if rgb is not None:
                return rgb
        except Exception:
            pass
        time.sleep(0.03)
    return None


def _parse_ppm(data):
    """解析 P6 PPM 头并返回 body RGB bytes，失败返回 None。"""
    try:
        idx = 0
        n = len(data)
        tokens = []
        while len(tokens) < 4 and idx < n:
            # 跳过注释（# 到行尾）
            if data[idx:idx + 1] == b'#':
                while idx < n and data[idx:idx + 1] not in (b'\n', b'\r'):
                    idx += 1
                continue
            start = idx
            while idx < n and data[idx:idx + 1] not in (b' ', b'\n', b'\r', b'\t'):
                idx += 1
            tokens.append(data[start:idx].decode())
            while idx < n and data[idx:idx + 1] in (b' ', b'\n', b'\r', b'\t'):
                idx += 1
        if len(tokens) < 4 or tokens[0] != 'P6':
            return None
        w, h = int(tokens[1]), int(tokens[2])
        body = data[idx:]
        need = w * h * 3
        if len(body) < need:
            return None
        return body[:need]      # RGB888 bytes
    except Exception:
        return None


def magick_jpeg(rgb, w, h, quality=78):
    cmd = ['magick', '-size', f'{w}x{h}', '-depth', '8', 'rgb:-',
           '-quality', str(quality), 'jpeg:-']
    return subprocess.run(cmd, input=rgb, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL).stdout


def write_ctrl(r, b):
    with open(CTRL_FILE, 'w') as f:
        f.write(f'R {r:.4f}\nB {b:.4f}\n')


def load_ctrl():
    r, b = 1.0, 1.0
    try:
        with open(CTRL_FILE) as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    if parts[0] in ('R', 'r'):
                        r = float(parts[1])
                    elif parts[0] in ('B', 'b'):
                        b = float(parts[1])
    except Exception:
        pass
    return r, b


HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>RGBIR 实时白平衡</title>
<style>
 body{font-family:sans-serif;background:#16181d;color:#e8e8e8;margin:18px}
 .card{background:#22252c;border-radius:12px;padding:16px 20px;max-width:460px;
       box-shadow:0 2px 10px rgba(0,0,0,.4)}
 h1{font-size:19px;margin:0 0 4px}
 .sub{color:#9aa0aa;font-size:12px;margin-bottom:14px}
 .row{display:flex;align-items:center;margin:12px 0}
 .row label{width:26px;font-weight:700}
 .row input[type=range]{flex:1;margin:0 12px;accent-color:#e0a020}
 .row .v{width:56px;text-align:right;font-variant-numeric:tabular-nums;color:#ffd27a}
 .bar{height:7px;border-radius:4px;overflow:hidden;background:#33373f;margin-top:4px}
 .bar>div{height:100%;background:linear-gradient(90deg,#b93,#e66)}
 .bar.r>div{background:linear-gradient(90deg,#933,#e55)}
 .bar.g>div{background:#3a4}
 .bar.b>div{background:linear-gradient(90deg,#339,#55e)}
 .hint{font-size:11px;color:#7c828d;margin-top:12px;line-height:1.5}
 img.cam{width:100%;max-width:560px;transform:scaleX(-1);border-radius:10px;
         background:#000;margin-top:14px}
 button{margin-top:12px;padding:8px 18px;border:0;border-radius:8px;background:#3a7bd5;
        color:#fff;font-size:14px;cursor:pointer}
#rgb b{width:12px;height:12px;display:inline-block;border-radius:3px;margin-right:6px}
</style></head><body>
<div class="card">
  <h1>RGBIR 实时白平衡调谐</h1>
  <div class="sub">滑块写入 /tmp/rgbir_wb，GPU debayer 每帧读取 → 画面即时变化</div>
  <div class="row"><label>R</label>
    <input id="sR" type="range" min="0.6" max="1.6" step="0.01" value="1">
    <span class="v" id="vR">1.00</span></div>
  <div class="row"><label>B</label>
    <input id="sB" type="range" min="0.6" max="1.6" step="0.01" value="1">
    <span class="v" id="vB">1.00</span></div>
  <div id="rgb"></div>
  <button id="rst">重置 (1.0)</button>
  <div class="hint">R 调大 → 画面偏红；B 调大 → 画面偏蓝。<br>
     之前整体偏绿，可先试 R≈1.15 B≈1.10。数值实时写入控制文件，无需重启。</div>
</div>
<img class="cam" id="cam" src="/stream">
<script>
const sR=document.getElementById('sR'), sB=document.getElementById('sB');
const vR=document.getElementById('vR'), vB=document.getElementById('vB');
const rgb=document.getElementById('rgb');
let m=null;   // [Ravg,Gavg,Bavg] 0-255 of latest frame
async function fetchM(){ try{const r=await fetch('/m'); m=await r.json();}catch(e){} }
function paint(){
  if(!m || m[1]<=0) return;
  const tot=m[1]; // 以 G 为基准，条长 = 通道/G
  const cols=['#e55','#3a4','#55e'], names=['R','G','B'];
  let s='';
  for(let i=0;i<3;i++){
    const w=Math.max(4, Math.min(100, m[i]/tot*100));
    s+='<div style="display:flex;align-items:center;margin:3px 0;">'+
       '<b style="width:18px;">'+names[i]+'</b>'+
       '<div class="bar" style="flex:1;"><div style="width:'+w+'%;background:'+cols[i]+'"></div></div>'+
       '<span style="width:52px;text-align:right;font-size:11px;color:#c9cdd4">'+
       (m[i]/tot).toFixed(2)+'</span></div>';
  }
  rgb.innerHTML=s;
}
function send(){
  const r=parseFloat(sR.value), b=parseFloat(sB.value);
  vR.textContent=r.toFixed(2); vB.textContent=b.toFixed(2);
  fetch('/set?r='+r+'&b='+b);
}
sR.oninput=send; sB.oninput=send;
document.getElementById('rst').onclick=()=>{sR.value=1;sB.value=1;send();};
async function init(){
  try{const r=await fetch('/get'); const s=await r.json();
      sR.value=s.r; sB.value=s.b; vR.textContent=s.r.toFixed(2); vB.textContent=s.b.toFixed(2);
  }catch(e){}
}
init();
fetchM(); setInterval(fetchM, 1500); setInterval(paint, 500);
</script></body></html>"""


def make_handler(cam_thread_started):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _write(self, data, ctype='application/json', code=200):
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if path in ('/', '/index.html'):
                self._write(HTML.encode(), 'text/html; charset=utf-8')
            elif path == '/set':
                q = parse_qs(parsed.query)
                r = float(q.get('r', ['1.0'])[0])
                b = float(q.get('b', ['1.0'])[0])
                r = min(4.0, max(0.001, r))
                b = min(4.0, max(0.001, b))
                with lock:
                    global cur_r, cur_b
                    cur_r, cur_b = r, b
                write_ctrl(r, b)
                self._write(json.dumps({'r': r, 'b': b,
                                        'file': CTRL_FILE}).encode())
            elif path == '/get':
                r, b = load_ctrl()
                self._write(json.dumps({'r': r, 'b': b,
                                        'file': CTRL_FILE}).encode())
            elif path == '/m':
                # 最新一帧 RGB 均值（三通道），供前端画 RGB 条
                data = read_latest_ppm()
                if data:
                    n3 = len(data)
                    R = G = B = 0
                    cnt = 0
                    # 抽样加速：隔 60 像素采样
                    for i in range(0, n3 - 2, 180):
                        R += data[i]; G += data[i + 1]; B += data[i + 2]
                        cnt += 1
                    means = [round(R / cnt, 1), round(G / cnt, 1),
                             round(B / cnt, 1)] if cnt else [0, 0, 0]
                    self._write(json.dumps(means).encode())
                else:
                    self._write(json.dumps([0, 0, 0]).encode())
            elif path == '/stream':
                self._stream()
            else:
                self._write(b'not found', 'text/plain', 404)

        def _stream(self):
            self.send_response(200)
            self.send_header('Content-Type',
                             'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            try:
                while True:
                    data = read_latest_ppm()
                    if data is None:
                        time.sleep(0.15)
                        continue
                    jpg = magick_jpeg(data, 1288, 972)
                    if not jpg:
                        time.sleep(0.05)
                        continue
                    self.wfile.write(b'--frame\r\n')
                    self.wfile.write(b'Content-Type: image/jpeg\r\n')
                    self.wfile.write(f'Content-Length: {len(jpg)}\r\n\r\n'.encode())
                    self.wfile.write(jpg)
                    self.wfile.write(b'\r\n')
                    self.wfile.flush()
                    time.sleep(0.02)
            except (BrokenPipeError, ConnectionResetError):
                pass

    return H


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    # 重置控制文件，避免残留旧值
    write_ctrl(1.0, 1.0)
    # 后台抓帧线程
    threading.Thread(target=run_cam, daemon=True).start()
    print('正在启动相机后台抓帧...')
    time.sleep(2.0)
    srv = ThreadingHTTPServer(('0.0.0.0', port), make_handler(None))
    print(f'实时白平衡工具已启动: http://localhost:{port}/')
    print(f'控制文件: {CTRL_FILE}  (debayer 每帧读取，实时生效)')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print('\n退出前重置控制文件为 1.0')
        write_ctrl(1.0, 1.0)


if __name__ == '__main__':
    main()

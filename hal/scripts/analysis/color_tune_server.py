#!/usr/bin/env python3
"""
OV5678 RGB-IR 交互式调色 GUI（浏览器版）
========================================
纯 Python 标准库(http.server) + 浏览器前端，无需安装任何 GUI 库/PIL/numpy。

功能：
  1) 启动本地 HTTP 服务器，读取 raw 并 demosaic 出「纯分离」基础 RGB
     （低分辨率预览传输到浏览器）
  2) 浏览器页面提供 滑块：R/G/B 增益、色相旋转、伽马校正
     —— 拖动滑块在前端 canvas 实时渲染（零延迟）
  3) 点「保存参数」把当前参数写入 <前缀>_params.txt
  4) 点「高清导出」用当前参数在后端重新 demosaic 全分辨率并写 <前缀>_color.png

用法：
  python3 color_tune_server.py in.raw out_prefix [端口] [OW OH]

  端口默认 8765。启动后用浏览器打开 http://localhost:8765/
  滑块调好满意后点保存参数 / 高清导出。Ctrl+C 关闭。

调色顺序与 color_tune.py 完全一致：增益 -> 伽马 -> 色相旋转。
"""
import sys, json, struct
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import demosaic_color as dc

# ---------- 全局状态 ----------
PREFIX = 'tuned'
W0 = H0 = 640  # 预览宽高（等比缩放传输到浏览器）
BASE = []      # 预览 base RGB 扁平列表 [r,g,b,...], 0-255
PRE_W = PRE_H = 0
ARGS_PARAMS = None

# ---------- 调色（与 color_tune.py 一致，供导出全分辨率用） ----------
def rgb_to_hsv(r, g, b):
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    mx = max(r, g, b); mn = min(r, g, b); d = mx - mn
    h = 0.0
    if d > 1e-9:
        if mx == r: h = 60 * (((g - b) / d) % 6)
        elif mx == g: h = 60 * ((b - r) / d + 2)
        else: h = 60 * ((r - g) / d + 4)
    s = 0.0 if mx == 0 else d / mx
    return h, s, mx

def hsv_to_rgb(h, s, v):
    h = h % 360
    c = v * s; x = c * (1 - abs(((h / 60) % 2) - 1)); m = v - c
    if h < 60:   r, g, b = c, x, 0
    elif h < 120: r, g, b = x, c, 0
    elif h < 180: r, g, b = 0, c, x
    elif h < 240: r, g, b = 0, x, c
    elif h < 300: r, g, b = x, 0, c
    else:        r, g, b = c, 0, x
    return int((r + m) * 255), int((g + m) * 255), int((b + m) * 255)

def tune_flat(flat, rg, gg, bg, hue, gamma, n):
    """对扁平 RGB 列表做增益->伽马->色相。flat: 0-255, n: 像素数。"""
    inv = 1.0 / gamma if gamma != 0 else 1.0
    use_gam = gamma != 1.0
    use_hue = hue != 0.0
    out = [0] * (n * 3)
    for i in range(n):
        r = flat[i*3] * rg; g = flat[i*3+1] * gg; b = flat[i*3+2] * bg
        if use_gam:
            r = 255.0 * ((r/255.0)**inv); g = 255.0 * ((g/255.0)**inv); b = 255.0 * ((b/255.0)**inv)
        if use_hue:
            h, s, v = rgb_to_hsv(r, g, b)
            r, g, b = hsv_to_rgb(h + hue, s, v)
        out[i*3] = min(255, max(0, int(r)))
        out[i*3+1] = min(255, max(0, int(g)))
        out[i*3+2] = min(255, max(0, int(b)))
    return out

# ---------- 加载数据 ----------
def load_preview(raw_path):
    global BASE, PRE_W, PRE_H
    dc.OW, dc.OH = ARGS_PARAMS['OW'], ARGS_PARAMS['OH']
    px = dc.read_raw(raw_path)
    cx, cy = dc.auto_screen_center(px)
    dc.CX, dc.CY = cx, cy
    dc.OX, dc.OY = cx - dc.OW//2, cy - dc.OH//2
    print(f"屏幕中心=({cx},{cy}) 裁切 {dc.OW}x{dc.OH}")
    rgb, _ = dc.demosaic_color(px, 1.0, 1.0)  # 纯分离 base
    # 等比缩小到预览尺寸（隔行取均值，简单用隔点）
    sw = dc.OW / W0
    sh = dc.OH / H0
    k = max(1, int((sw + sh) / 2))
    PRE_W = dc.OW // k
    PRE_H = dc.OH // k
    flat = []
    for y in range(PRE_H):
        sy = min(dc.OH - 1, y * k)
        for x in range(PRE_W):
            sx = min(dc.OW - 1, x * k)
            r, g, b = rgb[sy][sx]
            flat.extend((r, g, b))
    BASE = flat
    print(f"预览尺寸 {PRE_W}x{PRE_H}，像素数 {len(flat)//3}")

# ---------- HTTP 处理 ----------
def make_handler(raw_path):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send_json(self, obj):
            data = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.startswith('/preview'):
                self._send_json({
                    'w': PRE_W, 'h': PRE_H,
                    'base': BASE,
                })
            else:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                body = HTML.encode('utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def do_POST(self):
            n = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(n)
            try:
                params = json.loads(body)
            except Exception:
                params = {}
            rg = float(params.get('r', 1.0))
            gg = float(params.get('g', 1.0))
            bg = float(params.get('b', 1.0))
            hue = float(params.get('hue', 0.0))
            gamma = float(params.get('gamma', 1.0))
            action = params.get('action', '')
            if action == 'export':
                # 重新 demosaic 高分辨率并应用调色，写 PNG
                rgb, _ = dc.demosaic_color(dc_read_px(raw_path), 1.0, 1.0)
                tuned = [[0]*dc.OW for _ in range(dc.OH)]
                for y in range(dc.OH):
                    for x in range(dc.OW):
                        r2,g2,b2 = rgb[y][x]
                        r2=r2*rg; g2=g2*gg; b2=b2*bg
                        if gamma != 1.0:
                            inv=1.0/gamma
                            r2=255*((r2/255.0)**inv); g2=255*((g2/255.0)**inv); b2=255*((b2/255.0)**inv)
                        if hue:
                            h,s,v=rgb_to_hsv(r2,g2,b2); r2,g2,b2=hsv_to_rgb(h+hue,s,v)
                        tuned[y][x]=(min(255,max(0,int(r2))),min(255,max(0,int(g2))),min(255,max(0,int(b2))))
                dc.write_ppm_rgb(PREFIX + '_color.ppm', tuned)
                dc.to_png(PREFIX + '_color.ppm', PREFIX + '_color.png')
                self._send_json({'ok': True, 'png': PREFIX + '_color.png', 'params': params})
            else:
                # save params
                with open(PREFIX + '_params.txt', 'w') as f:
                    f.write(f"r_gain={rg:.4f}\ng_gain={gg:.4f}\nb_gain={bg:.4f}\n"
                            f"hue={hue:.2f}\ngamma={gamma:.4f}\n")
                self._send_json({'ok': True, 'saved': PREFIX + '_params.txt', 'params': params})
    return H

# 缓存已读取的 raw 全像素，避免重复读盘
_PX_CACHE = {}
def dc_read_px(path):
    if path not in _PX_CACHE:
        _PX_CACHE[path] = dc.read_raw(path)
    return _PX_CACHE[path]

# ---------- 前端 HTML/JS ----------
HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>OV5678 调色</title>
<style>
 body{font-family:system-ui,sans-serif;background:#1e1e2e;color:#eee;margin:0;display:flex;height:100vh}
 .side{width:300px;background:#27273d;padding:16px;box-sizing:border-box;overflow-y:auto}
 .main{flex:1;display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box}
 canvas{max-width:100%;max-height:100%;background:#000;border:1px solid #444}
 h1{font-size:16px;margin:0 0 8px}
 .ctrl{margin:10px 0}
 .ctrl label{display:flex;justify-content:space-between;font-size:12px;margin-bottom:2px}
 input[type=range]{width:100%}
 .btns{margin-top:14px}
 button{width:100%;padding:8px;margin:4px 0;border:0;border-radius:6px;font-size:13px;cursor:pointer}
 .exp{background:#4caf50;color:#fff}.sav{background:#2196f3;color:#fff}
 .status{font-size:11px;color:#9a9;margin-top:8px;white-space:pre-wrap;word-break:break-all}
</style></head><body>
<div class="side">
 <h1>OV5678 RGB-IR 调色</h1>
 <div class="ctrl"><label>R 增益 <span id="vr">1.00</span></label>
  <input type="range" id="r" min="0.2" max="3" step="0.01" value="1"></div>
 <div class="ctrl"><label>G 增益 <span id="vg">1.00</span></label>
  <input type="range" id="g" min="0.2" max="3" step="0.01" value="1"></div>
 <div class="ctrl"><label>B 增益 <span id="vb">1.00</span></label>
  <input type="range" id="b" min="0.2" max="3" step="0.01" value="1"></div>
 <div class="ctrl"><label>色相旋转 <span id="vh">0°</span></label>
  <input type="range" id="hue" min="-180" max="180" step="1" value="0"></div>
 <div class="ctrl"><label>伽马 <span id="vgam">1.00</span></label>
  <input type="range" id="gam" min="0.3" max="2.5" step="0.01" value="1"></div>
 <div class="btns">
  <button class="sav" onclick="saveParams()">保存参数</button>
  <button class="exp" onclick="exportPng()">高清导出 PNG</button>
 </div>
 <div class="status" id="status">加载中…</div>
</div>
<div class="main"><canvas id="cv"></canvas></div>
<script>
let W=0,H=0,base=null,cv,ctx,img;
function rgb2hsv(r,g,b){r/=255;g/=255;b/=255;let mx=Math.max(r,g,b),mn=Math.min(r,g,b),d=mx-mn,h=0;
 if(d>1e-9){if(mx==r)h=60*(((g-b)/d)%6+6)%6;else if(mx==g)h=60*((b-r)/d+2);else h=60*((r-g)/d+4);}
 let s=mx==0?0:d/mx;return [h,s,mx];}
function hsv2rgb(h,s,v){h=((h%360)+360)%360;let c=v*s,x=c*(1-Math.abs(((h/60)%2)-1)),m=v-c,r,g,b;
 if(h<60){r=c;g=x;b=0}else if(h<120){r=x;g=c;b=0}else if(h<180){r=0;g=c;b=x}
 else if(h<240){r=0;g=x;b=c}else if(h<300){r=x;g=0;b=c}else{r=c;g=0;b=x}
 return [Math.round((r+m)*255),Math.round((g+m)*255),Math.round((b+m)*255)];}
function vals(){return {r:+r.value,g:+g.value,b:+b.value,hue:+hue.value,gamma:+gam.value};}
function render(){
 v=vals(); let d=img.data,n=W*H;
 let inv=1/v.gamma,useGam=v.gamma!=1,useHue=v.hue!=0;
 // base 是 0-255 RGB 扁平列表；输出到 RGBA 的 ImageData（每像素4字节，A=255）
 for(let i=0;i<n;i++){
  let r=base[i*3]*v.r, gg=base[i*3+1]*v.g, bl=base[i*3+2]*v.b;
  if(useGam){r=255*Math.pow(r/255,inv);gg=255*Math.pow(gg/255,inv);bl=255*Math.pow(bl/255,inv);}
  if(useHue){let hsv=rgb2hsv(r,gg,bl);let q=hsv2rgb(hsv[0]+v.hue,hsv[1],hsv[2]);r=q[0];gg=q[1];bl=q[2];}
  let k=i*4;
  d[k]=r<0?0:r>255?255:r; d[k+1]=gg<0?0:gg>255?255:gg;
  d[k+2]=bl<0?0:bl>255?255:bl; d[k+3]=255;
 }
 ctx.putImageData(img,0,0);
 document.getElementById('vr').textContent=v.r.toFixed(2);
 document.getElementById('vg').textContent=v.g.toFixed(2);
 document.getElementById('vb').textContent=v.b.toFixed(2);
 document.getElementById('vh').textContent=v.hue+'°';
 document.getElementById('vgam').textContent=v.gamma.toFixed(2);
}
let raf=null;
function schedule(){clearTimeout(raf);raf=setTimeout(render,16);}
['r','g','b','hue','gam'].forEach(id=>document.getElementById(id).addEventListener('input',schedule));
async function saveParams(){let v=vals();let r=await fetch('/',{method:'POST',body:JSON.stringify({action:'save',...v})});let j=await r.json();
 document.getElementById('status').textContent='已保存: '+JSON.stringify(j.saved)+'\\n'+JSON.stringify(v);}
async function exportPng(){let v=vals();let r=await fetch('/',{method:'POST',body:JSON.stringify({action:'export',...v})});let j=await r.json();
 document.getElementById('status').textContent='已导出: '+j.png+'\\n'+JSON.stringify(v);}
(async()=>{let r=await fetch('/preview');let j=await r.json();W=j.w;H=j.h;base=j.base;
 cv=document.getElementById('cv');cv.width=W;cv.height=H;ctx=cv.getContext('2d');
 img=ctx.createImageData(W,H);img.data=new Uint8ClampedArray(W*H*4);
 document.getElementById('status').textContent=W+'x'+H+' 加载完成，拖动滑块实时调色';
 render();})();
</script></body></html>
"""


def main():
    global PREFIX, ARGS_PARAMS
    if len(sys.argv) < 3:
        raise SystemExit("用法: python3 color_tune_server.py in.raw out_prefix [端口] [OW OH]\n"
                         "  启动后用浏览器打开 http://localhost:端口/")
    raw_path, PREFIX = sys.argv[1], sys.argv[2]
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 8765
    OW, OH = 1200, 900
    if len(sys.argv) > 5:
        OW = int(sys.argv[4]); OH = int(sys.argv[5])
    ARGS_PARAMS = {'OW': OW, 'OH': OH}
    load_preview(raw_path)
    # 预读全分辨率像素到缓存
    dc_read_px(raw_path)
    print(f"\n浏览器打开: http://localhost:{port}/\n（滑块实时调色；保存参数 / 高清导出；Ctrl+C 退出）")
    ThreadingHTTPServer(('127.0.0.1', port), make_handler(raw_path)).serve_forever()


if __name__ == '__main__':
    main()

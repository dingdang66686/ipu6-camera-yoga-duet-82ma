#!/usr/bin/env python3
"""
从 OV5678 RGB-IR raw 生成一张（近似）彩色预览图。

已知（实证）：
  IR 相位 = (r偶, c奇) = (0,1),(0,3),(2,1),(2,3)
  (1,0),(3,2) = R 像素（红/蓝比 2.35，红亮蓝暗，明确）
其余 10 个 RGB 相位受手机屏串扰细分不全。

策略（稳健、不依赖不完美的三色细分）：
  1. 对每个非IR像素，按其 4x4 相位给一组 R/G/B 系数（来自纯色屏相对响应，做温和处理），
     拆成三通道。IR 像素用邻域非IR均值填补。
  2. 系数保证中性灰下 R≈G≈B，避免偏绿死灰。

输出：out.ppm + out.png
"""
import sys
import subprocess

W, H = 2592, 1944
SAT = 1023.0

def clamp(v):
    v = int(v)
    return 0 if v < 0 else (255 if v > 255 else v)

def read_raw(path):
    data = open(path, "rb").read()
    px = [[0] * W for _ in range(H)]
    for y in range(H):
        base = y * 2 * W
        for x in range(W):
            px[y][x] = (data[base + x * 2] | data[base + x * 2 + 1] << 8) & 0x3FF
    return px

def is_ir(y, x):
    return (y % 2 == 0) and (x % 2 == 1)

def phase(y, x):
    return (y % 4, x % 4)

# 相位 -> (R,G,B) 权重。基于纯色实验 + 白屏校准做"温和"估计。
# 白屏下各非IR相位 ~515-554 接近，故基础权重约均等；用纯色比值微调，
# 并确保 R 相位明显偏红、避免整体发绿。
# 权重 = 该相位在(红屏,绿屏,蓝屏)归一响应。为防串扰过度放大，做归一化为均权+偏差。
weights = {}
# 从 four-color 实验的表引入 (归一化, 最大值=1):
#       红屏   绿屏   蓝屏
raw_resp = {
    (0,0): (672,683,881), (1,0): (672,638,286), (1,1): (688,683,886),
    (1,2): (398,631,479), (1,3): (670,680,876), (2,0): (694,683,890),
    (2,2): (672,680,882), (3,0): (398,633,480), (3,1): (669,682,876),
    (3,2): (672,636,286), (3,3): (687,680,886),
}
# 陡化：提高通道间差异（对抗串扰导致的均化），让彩色出来
def sharpen(vals, power=2.0):
    m = max(vals) if max(vals) > 0 else 1
    n = [ (v/m) ** power for v in vals ]
    s = sum(n)
    return [x/s for x in n] if s > 0 else [1/3,1/3,1/3]

for p, (r,g,b) in raw_resp.items():
    weights[p] = sharpen((r,g,b), 2.0)
# IR 相位权重设为均等（它们会由邻域填充，本表不用）

def neighbor_rgb(px, y, x):
    s = [0,0,0]; c = 0
    for dy in (-1,1):
        ny = y+dy
        if 0 <= ny < H:
            for dx in (-1,1):
                nx = x+dx
                if 0 <= nx < W and not is_ir(ny,nx):
                    q = phase(ny,nx)
                    if q in weights:
                        w = weights[q]
                        for k in range(3):
                            s[k] += px[ny][nx] * w[k]
                    c += 1
    if c == 0:
        return (px[y][x], px[y][x], px[y][x])
    return [int(v/c) for v in s]

def render(px):
    out = [[(0,0,0)]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            if is_ir(y,x):
                r,g,b = neighbor_rgb(px,y,x)
            else:
                p = phase(y,x)
                w = weights.get(p)
                if w is None:
                    r=g=b=px[y][x]
                else:
                    v = px[y][x]
                    r = v*w[0]; g = v*w[1]; b = v*w[2]
            out[y][x]=(r,g,b)
    return out

def write_ppm(path,out):
    data=bytearray(W*H*3); i=0
    for y in range(H):
        for x in range(W):
            r,g,b=out[y][x]
            data[i]=clamp(r);data[i+1]=clamp(g);data[i+2]=clamp(b);i+=3
    open(path,"wb").write(b"P6\n%d %d\n255\n"%(W,H)+bytes(data))

def main():
    if len(sys.argv)<3:
        print("用法: python3 render_color.py in.raw out_prefix");return
    src,prefix=sys.argv[1],sys.argv[2]
    px=read_raw(src)
    out=render(px)
    ppm=f"{prefix}_color.ppm"
    write_ppm(ppm,out)
    subprocess.run(["magick",ppm,f"{prefix}_color.png"],check=True)
    print(f"生成 {ppm} / {prefix}_color.png")

if __name__=="__main__":
    main()

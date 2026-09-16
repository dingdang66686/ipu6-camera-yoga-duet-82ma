#!/usr/bin/env python3
"""Analyze highlight (near-saturated) regions of captured PPM frames.

For each frame: load PPM, compute luminance, find pixels with luminance in
highlight transition bands (not fully saturated, but bright), and report the
R/G, B/G ratios in those bands. This reveals whether highlights are going
green (R/G<1 or B/G<1) before full saturation.

Usage: python3 analyze_highlights.py <ppm> [<ppm> ...]
"""
import sys, numpy as np

def load_ppm(path):
    b = open(path, 'rb').read()
    assert b[:2] == b'P6', path
    i = 2
    def token():
        nonlocal i
        while b[i:i+1] in b' \t\r\n':
            i += 1
        if b[i:i+1] == b'#':
            while b[i:i+1] != b'\n':
                i += 1
            return token()
        j = i
        while b[j:j+1] not in b' \t\r\n':
            j += 1
        s = b[i:j]; i = j
        return s
    w = int(token()); h = int(token()); mx = int(token())
    i += 1
    data = np.frombuffer(b[i:i+w*h*3], dtype=np.uint8).reshape(h, w, 3).astype(float)
    return w, h, data

def analyze(path):
    w, h, a = load_ppm(path)
    r, g, bl = a[...,0], a[...,1], a[...,2]
    lum = np.maximum(np.maximum(r, g), bl)  # max channel ~ brightness
    total = a.shape[0]*a.shape[1]
    print(f"\n=== {path.split('/')[-1]}  {w}x{h} ===")
    # full saturation fraction (all channels near 255)
    full = (lum >= 250).mean()*100
    print(f"  fully-saturated(>=250): {full:.2f}%  max={a.max():.0f}  mean={a.mean():.1f}")
    # highlight transition bands
    for lo, hi, name in [(60,100,'lo'), (100,150,'mid'), (150,200,'hi'),
                         (200,240,'hi-trans'), (240,250,'near-sat')]:
        m = (lum >= lo) & (lum < hi)
        if m.sum() < 50:
            print(f"  band lum[{lo},{hi})  {name:10s}: n={m.sum():6d}  (skip, too few)")
            continue
        rn = r[m]; gn = g[m]; bln = bl[m]
        rg = (rn/gn)[gn>0]
        bg = (bln/gn)[gn>0]
        print(f"  band lum[{lo},{hi})  {name:10s}: n={m.sum():6d}  "
              f"R/G={rg.mean():.3f}  B/G={bg.mean():.3f}  "
              f"meanR={rn.mean():.0f} meanG={gn.mean():.0f} meanB={bln.mean():.0f}  "
              f"excessG={(gn-rn).mean():+.1f},{(gn-bln).mean():+.1f}")

for p in sys.argv[1:]:
    analyze(p)

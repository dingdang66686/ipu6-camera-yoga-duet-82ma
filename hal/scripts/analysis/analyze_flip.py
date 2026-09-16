import numpy as np, glob, sys

def load_ppm(path):
    b = open(path, 'rb').read()
    i = 2
    def tok():
        nonlocal i
        while b[i:i+1] in b' \t\r\n': i += 1
        if b[i:i+1] == b'#':
            while b[i:i+1] != b'\n': i += 1
            return tok()
        j = i
        while b[j:j+1] not in b' \t\r\n': j += 1
        s = b[i:j]; i = j
        return s
    w = int(tok()); h = int(tok()); int(tok())
    i += 1
    return np.frombuffer(b[i:i+w*h*3], dtype=np.uint8).reshape(h, w, 3).astype(float)

def ana(files, label):
    print(label)
    for f in sorted(files)[:3]:
        a = load_ppm(f); r, g, bl = a[...,0], a[...,1], a[...,2]
        m = np.maximum(g, 1)
        print(f"  {f.split('/')[-1]}: max={a.max():.0f} R/G={np.nanmean(r/m):.3f} B/G={np.nanmean(bl/m):.3f} "
              f"Rmean={r.mean():.0f} Gmean={g.mean():.0f} Bmean={bl.mean():.0f}")

ana(glob.glob('/tmp/frontstd/*.ppm'), 'FRONT std  (R/B FLIPPED):')
ana(glob.glob('/tmp/frontcls/*.ppm'), 'FRONT cls  (R/B FLIPPED):')

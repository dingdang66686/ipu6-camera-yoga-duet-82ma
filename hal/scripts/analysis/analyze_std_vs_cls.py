import numpy as np, glob, sys

def load_ppm(path):
    b = open(path, 'rb').read()
    # parse P6 header
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
    # skip exactly one whitespace char after maxval
    i += 1
    data = np.frombuffer(b[i:i+w*h*3], dtype=np.uint8).reshape(h, w, 3).astype(float)
    return w, h, data

def ana(files, label):
    print(label)
    for f in sorted(files)[:3]:
        w, h, a = load_ppm(f)
        r, g, bl = a[..., 0], a[..., 1], a[..., 2]
        m = np.maximum(g, 1)
        print(f"  {f.split('/')[-1]}: {w}x{h} max={a.max():.1f} "
              f"R/G={np.nanmean(r/m):.3f} B/G={np.nanmean(bl/m):.3f} "
              f"Rmean={r.mean():.1f} Gmean={g.mean():.1f} Bmean={bl.mean():.1f}  nz={(a>0).sum()}")

ana(glob.glob('/tmp/fhstd/s-*.ppm'), 'STD:')
ana(glob.glob('/tmp/fhcls/c-*.ppm'), 'CLS:')

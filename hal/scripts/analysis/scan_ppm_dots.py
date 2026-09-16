import numpy as np, sys
from numpy.lib.stride_tricks import sliding_window_view
fn=sys.argv[1]
import re
with open(fn,'rb') as f:
    data=f.read()
m=re.match(rb'P6\s+(\d+)\s+(\d+)\s+(\d+)\s*',data,re.S)
W,H,mx=[int(x) for x in m.groups()]
pix=np.frombuffer(data[m.end():],dtype=np.uint8).reshape(H,W,3)
rgb=pix.astype(np.int16)
print(f'{fn}: {W}x{H}')
def medp(a):
    a=np.pad(a,2,mode='edge')
    return np.median(sliding_window_view(a,(5,5)),axis=(-2,-1))
r,g,b=rgb[...,0],rgb[...,1],rgb[...,2]
mxv=np.maximum.reduce([r,g,b]); mn=np.minimum.reduce([r,g,b]); sat=mxv-mn
rmed,gmed,bmed=medp(r),medp(g),medp(b)
dv=np.maximum.reduce([np.abs(r-rmed),np.abs(g-gmed),np.abs(b-bmed)])
# 孤立彩点: 高饱和 且 偏离局部大
mask=(sat>60)&(dv>80)
mask[:2]=0;mask[-2:]=0;mask[:,:2]=0;mask[:,-2:]=0
ys,xs=np.nonzero(mask)
# 聚类
pts=set(zip(xs.tolist(),ys.tolist())); cl=[]
while pts:
    seed=pts.pop(); stack=[seed]; c=[]
    while stack:
        x,y=stack.pop(); c.append((x,y))
        for dx in(-1,0,1):
            for dy in(-1,0,1):
                p=(x+dx,y+dy)
                if p in pts: pts.discard(p); stack.append(p)
    cl.append(c)
print(f'  孤立彩点候选={len(ys)} 聚成{len(cl)}簇')
for c in sorted(cl,key=len,reverse=True)[:12]:
    x,y=c[0]
    print('   %dpx @(%d,%d) rgb=(%d,%d,%d) nbr=(%d,%d,%d) sat=%d'%(len(c),x,y,r[y,x],g[y,x],b[y,x],rmed[y,x],gmed[y,x],bmed[y,x],sat[y,x]))

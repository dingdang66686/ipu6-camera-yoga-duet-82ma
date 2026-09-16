import numpy as np, sys
from numpy.lib.stride_tricks import sliding_window_view
fn='hz_rgb.raw'; H,W=720,1280
rgb=np.frombuffer(open(fn,'rb').read(),dtype=np.uint8).reshape(H,W,3).astype(np.int16)
print('后置.jpeg (1280x720) 检测')
def medp(a,k=3):
    p=1 if k==3 else 2
    a=np.pad(a,p,mode='edge')
    return np.median(sliding_window_view(a,(k,k)),axis=(-2,-1))
# 1) 直接查我已知的3个坏点
print('=== 已知3坏点坐标在 后置.jpeg 的值 ===')
for x,y in [(1152,77),(1263,396),(632,534)]:
    r,g,b=rgb[y,x]
    nr,ng,nb=[medp(rgb[...,i],3)[y,x] for i in range(3)]
    print('  (%d,%d) rgb=(%d,%d,%d) nbr3=(%d,%d,%d) sat=%d'%(x,y,r,g,b,nr,ng,nb,int(max(r,g,b)-min(r,g,b))))
# 2) 全图孤立彩点扫描
print('=== 全图孤立彩点(3x3) ===')
r,g,b=rgb[...,0],rgb[...,1],rgb[...,2]
mx=np.maximum.reduce([r,g,b]); mn=np.minimum.reduce([r,g,b]); sat=mx-mn
rmed,gmed,bmed=[medp(rgb[...,i],3) for i in range(3)]
dv=np.maximum.reduce([np.abs(r-rmed),np.abs(g-gmed),np.abs(b-bmed)])
mask=(sat>50)&(dv>70)
mask[:1]=0;mask[-1:]=0;mask[:,:1]=0;mask[:,-1:]=0
ys,xs=np.nonzero(mask)
print('  候选像素=',len(ys))
pts=set(zip(xs.tolist(),ys.tolist())); cl=[]
while pts:
    seed=pts.pop();stack=[seed];c=[]
    while stack:
        x,y=stack.pop();c.append((x,y))
        for dx in(-1,0,1):
            for dy in(-1,0,1):
                p=(x+dx,y+dy)
                if p in pts: pts.discard(p);stack.append(p)
    cl.append(c)
print('  聚类=',len(cl))
for c in sorted(cl,key=len,reverse=True)[:20]:
    x,y=c[0]
    print('   %dpx@(%d,%d) rgb=(%d,%d,%d) nbr=(%d,%d,%d) sat=%d'%(len(c),x,y,r[y,x],g[y,x],b[y,x],rmed[y,x],gmed[y,x],bmed[y,x],sat[y,x]))

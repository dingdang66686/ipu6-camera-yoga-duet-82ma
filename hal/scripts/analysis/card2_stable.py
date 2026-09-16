import numpy as np, re, sys
from numpy.lib.stride_tricks import sliding_window_view
NF=30;W,H=2584,1944
def load(i):
    fn='card2_rgbcam0-stream0-%06d.ppm'%i
    data=open(fn,'rb').read()
    m=re.match(rb'P6\s+(\d+)\s+(\d+)\s+(\d+)\s*',data,re.S)
    wv,hv,mx=[int(x) for x in m.groups()]
    return np.frombuffer(data[m.end():],dtype=np.uint8).reshape(hv,wv,3).astype(np.int16)
def medp(a):
    a=np.pad(a,2,mode='edge')
    return np.median(sliding_window_view(a,(5,5)),axis=(-2,-1))
# 每帧孤立亮点(任一通道-局部>90, 且该像素是局部极大高)
count=np.zeros((H,W),dtype=np.int16)
for i in range(NF):
    px=load(i)
    r,g,b=px[...,0],px[...,1],px[...,2]
    mxv=np.maximum.reduce([r,g,b])
    rmed,gmed,bmed=medp(r),medp(g),medp(b)
    mxmed=np.maximum.reduce([rmed,gmed,bmed])
    # 亮点: 自身亮度比局部中值高很多
    m=(mxv-mxmed>90)
    m[:3]=0;m[-3:]=0;m[:,:3]=0;m[:,-3:]=0
    count+=m
# 跨帧稳定
ys,xs=np.nonzero(count>=(NF*0.7))
print(f'card2后置 改驱动前: 跨{NF}帧稳定孤立亮点(>70%) = {len(ys)}')
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
print(f'聚类={len(cl)}')
im=np.load([None]) if False else load(0)
r,g,b=im[...,0],im[...,1],im[...,2]
rmed,gmed,bmed=medp(r),medp(g),medp(b)
for c in sorted(cl,key=len,reverse=True)[:25]:
    x,y=c[0]
    mxv=np.max([r[y,x],g[y,x],b[y,x]]); mn=np.min([r[y,x],g[y,x],b[y,x]])
    print('   %dpx @(%d,%d) rgb=(%d,%d,%d) nbr=(%d,%d,%d) stab=%d'%(len(c),x,y,r[y,x],g[y,x],b[y,x],rmed[y,x],gmed[y,x],bmed[y,x],count[y,x]))

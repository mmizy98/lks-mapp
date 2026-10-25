import json
from floors import F
ORDER=['1a','1','2','3','4','5','6','7','8','9','10','11']
vec={}; seed={}
def proj(c,x,y):
    x0,y0,x1,y1=c
    if (x1-x0)>=(y1-y0): return (min(max(x,x0+4),x1-4),(y0+y1)/2)
    return ((x0+x1)/2,min(max(y,y0+4),y1-4))
def dist(c,x,y):
    x0,y0,x1,y1=c; dx=max(x0-x,0,x-x1); dy=max(y0-y,0,y-y1); return (dx*dx+dy*dy)**.5
for f in ORDER:
    d=F[f]; corr=d['corr']; nodes=[]; edges=[]; pts={i:[] for i in range(len(corr))}; nid=[0]
    def nn(t,x,y,l=None,pre='n'):
        nid[0]+=1; n={'id':f'{pre}{f}_{nid[0]}','t':t,'x':round(x),'y':round(y)}
        if l: n['l']=l
        nodes.append(n); return n
    def attach(n,x,y):
        ci=min(range(len(corr)),key=lambda i:dist(corr[i],x,y)); px,py=proj(corr[ci],x,y)
        c=nn('c',px,py,pre='c'); pts[ci].append(c); edges.append([n['id'],c['id']])
    rooms=[]
    for (l,x0,x1,y0,y1,k,al) in d['rooms']:
        rooms.append({'l':l,'x':x0,'y':y0,'w':x1-x0,'h':y1-y0,'k':k,**({'al':list(al)} if al else {})})
        if k in ('room','place') and l:
            labs=[l]+list(al) if k=='room' else list(al)+[l]
            for i,lab in enumerate(labs):
                fx=x0+(x1-x0)*(i+1)/(len(labs)+1) if len(labs)>1 else (x0+x1)/2
                ci=min(range(len(corr)),key=lambda j:dist(corr[j],fx,(y0+y1)/2)); c=corr[ci]
                if y1<=c[1]+4: dy=y1
                elif y0>=c[3]-4: dy=y0
                else: dy=(y0+y1)/2
                if dy==(y0+y1)/2 and (c[2]-c[0])<(c[3]-c[1]):
                    fx = x1 if x1<=c[0]+4 else x0 if x0>=c[2]-4 else fx
                n=nn('r',fx,dy,lab,'r'); attach(n,fx,dy)
    for (l,x,y) in d['st']: attach(nn('s',x,y,l,'s'),x,y)
    pstarts=[]
    for (A,B,w) in d.get('paths',[]):
        a_=nn('c',*A,pre='c'); b_=nn('c',*B,pre='c'); edges.append([a_['id'],b_['id']])
        ci=min(range(len(corr)),key=lambda i:dist(corr[i],*B)); px,py=proj(corr[ci],*B); c=nn('c',px,py,pre='c'); pts[ci].append(c); edges.append([b_['id'],c['id']])
        pstarts.append(a_)
    for (l,x,y) in d['ent']:
        e=nn('e',x,y,l,'e'); near=[p for p in pstarts if ((p['x']-x)**2+(p['y']-y)**2)**.5<60]
        if near: edges.append([e['id'],near[0]['id']])
        else: attach(e,x,y)
    # junctions between touching corridors
    for i in range(len(corr)):
        for j in range(i+1,len(corr)):
            a,b=corr[i],corr[j]
            if a[0]<=b[2]+6 and b[0]<=a[2]+6 and a[1]<=b[3]+6 and b[1]<=a[3]+6:
                ix=(max(a[0],b[0])+min(a[2],b[2]))/2; iy=(max(a[1],b[1])+min(a[3],b[3]))/2
                pa=proj(a,ix,iy); pb=proj(b,ix,iy)
                na=nn('c',*pa,pre='c'); nb=nn('c',*pb,pre='c'); pts[i].append(na); pts[j].append(nb); edges.append([na['id'],nb['id']])
    for i,c in enumerate(corr):
        x0,y0,x1,y1=c; hor=(x1-x0)>=(y1-y0)
        e1=nn('c',*proj(c,x0,y0),pre='c'); e2=nn('c',*proj(c,x1,y1),pre='c'); P=pts[i]+[e1,e2]
        P.sort(key=lambda n:n['x'] if hor else n['y'])
        for a,b in zip(P,P[1:]): edges.append([a['id'],b['id']])
    vec[f]={'outline':' '.join(d['out']),'corr':[{'x':c[0],'y':c[1],'w':c[2]-c[0],'h':c[3]-c[1]} for c in corr],'rooms':rooms,
            'deco':[{'x':a,'y':b,'w':c-a,'h':e-b} for a,b,c,e in d['deco']],'ent':[{'l':l,'x':x,'y':y} for l,x,y in d['ent']],'paths':[{'a':A,'b':B,'w':w} for A,B,w in d.get('paths',[])],'labels':[{'t':t,'x':x,'y':y} for t,x,y in d['lab']]}
    seed[f]={'nodes':nodes,'edges':edges}
    print(f,len(rooms),len(nodes))
json.dump(vec,open('vec.json','w'),ensure_ascii=False,separators=(',',':'))
json.dump(seed,open('seed.json','w'),ensure_ascii=False,separators=(',',':'))

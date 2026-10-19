import sys,re,pymupdf,json,collections,statistics as st
sys.stdout.reconfigure(encoding='utf-8')
norm=lambda s: re.sub(r'\s+','',s)
def spans(doc,n,scale=1.0,xoff=0):
    out=[]
    for b in doc[n].get_text('dict')['blocks']:
        for l in b.get('lines',[]):
            sp=[s for s in l['spans'] if norm(s['text'])]
            if not sp: continue
            t=''.join(s['text'] for s in sp); s0=sp[0]
            out.append((s0['origin'][1]*scale,(s0['origin'][0]-xoff)*scale,norm(t),s0['size']*scale,s0['font']))
    return out
def cmp(h,o,pages,nup=1):
    H=pymupdf.open(h);O=pymupdf.open(o); rows=[]
    for pg in range(min(pages,len(O))):
        if nup==1: A=spans(H,pg)
        else:
            sheet,half=divmod(pg,nup); w=H[sheet].rect.width
            sc=595.28/(w/nup); A=[(y*sc,x*sc,t,s*sc,f) for (y,x,t,s,f) in spans(H,sheet) if x>=half*w/nup and x<(half+1)*w/nup]
            A=[(y,x-half*595.28,t,s,f) for (y,x,t,s,f) in A]
        B=spans(O,pg); used=set()
        for y,x,t,s,f in A:
            if len(t)<4: continue
            c=[(abs(yy-y)+abs(xx-x),j) for j,(yy,xx,tt,ss,ff) in enumerate(B) if j not in used and tt[:6]==t[:6] and abs(xx-x)<40 and abs(yy-y)<30]
            if not c: continue
            _,j=min(c); used.add(j); yy,xx,tt,ss,ff=B[j]; rows.append((round(s*2)/2,yy-y,xx-x,pg))
    return rows
if __name__=='__main__':
    h,o,pages,nup=sys.argv[1],sys.argv[2],int(sys.argv[3]),int(sys.argv[4])
    rows=cmp(h,o,pages,nup)
    by=collections.defaultdict(list)
    for s,dy,dx,pg in rows: by[s].append((dy,dx))
    print('줄',len(rows),'평균 dy %.2f dx %.2f'%(st.mean(r[1] for r in rows),st.mean(r[2] for r in rows)))
    for s in sorted(by): 
        v=by[s]; print('글자 %4.1fpt  %3d줄  dy 평균 %+5.2f (중앙 %+5.2f)  dx 평균 %+5.2f'%(s,len(v),st.mean(a for a,b in v),st.median(a for a,b in v),st.mean(b for a,b in v)))

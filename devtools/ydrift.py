"""한컴 PDF 쪽과 우리 PDF 쪽의 같은 글 줄(앞 8글자)을 짝지어 줄 y 차이(Δ)와 그 증가분을 찍는다. 증가분이 크게 뛰는 줄(<<<) 바로 위의 개체가 쪽 수 어긋남의 원인 후보.
    python devtools/ydrift.py 한컴.pdf 쪽 우리.pdf 쪽        (쪽은 1부터)"""
import sys, re, pymupdf
norm=lambda s: re.sub(r'\s+','',s)
def lines(doc,n):
    out=[]
    for b in doc[n-1].get_text('dict')['blocks']:
        for l in b.get('lines',[]):
            t=''.join(s['text'] for s in l['spans']); 
            if norm(t): out.append((l['bbox'][1],l['bbox'][0],norm(t)))
    return sorted(out)
def main(h,hp,o,op):
    A=lines(pymupdf.open(h),hp); B=lines(pymupdf.open(o),op)
    used=set(); prev=None
    print('한컴 y | 우리 y | Δ | 변화 | 글')
    for y,x,t in A:
        if len(t)<4: continue
        c=[(abs(yy-y),j) for j,(yy,xx,tt) in enumerate(B) if j not in used and tt[:8]==t[:8] and abs(xx-x)<40]
        if not c: continue
        d,j=min(c); used.add(j); yy=B[j][0]; dl=yy-y
        step='' if prev is None else f'{dl-prev:+.1f}'
        flag=' <<<' if prev is not None and abs(dl-prev)>3 else ''
        print(f'{y:7.1f} {yy:7.1f} {dl:+7.1f} {step:>7}{flag} {t[:30]}')
        prev=dl
main(sys.argv[1],int(sys.argv[2]),sys.argv[3],int(sys.argv[4]))

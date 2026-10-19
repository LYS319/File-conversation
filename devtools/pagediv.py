import json,pymupdf,re,os,sys
sys.stdout.reconfigure(encoding='utf-8')
norm=lambda s: re.sub(r'\s+','',s)
def lines(p):
    out=[]
    for b in p.get_text('dict')['blocks']:
        for l in b.get('lines',[]):
            sp=[s for s in l['spans'] if s['text'].strip()]
            if sp: out.append((round(sp[0]['origin'][1],1),norm(''.join(s['text'] for s in sp)),sp[0]['size']))
    out.sort(); return out
ms=[m for m in json.load(open('corpus/rhwp2/manifest.json',encoding='utf-8')) if 'oracle_pdf' in m]
d=json.load(open('corpus/_eval/rhwp2_fin11/eval.json',encoding='utf-8'))
only=sys.argv[1:]
for i,r in enumerate(d):
    if 'ref' not in r or r.get('suspect') or r['ref']==r['ours']: continue
    if only and str(i) not in only: continue
    H=pymupdf.open('corpus/rhwp2/'+ms[i]['oracle_pdf']); f=[f for f in os.listdir('corpus/_eval/rhwp2_fin11') if f.startswith('%03d_'%i) and f.endswith('.pdf')][0]; O=pymupdf.open('corpus/_eval/rhwp2_fin11/'+f)
    # words sets to find first page where the *set of line starts* differ
    def key(p):
        L=[t for y,t,s in lines(p) if 60<y<780 and len(t)>5]
        return L[0][:10] if L else ''
    div=None
    for n in range(min(len(H),len(O))):
        if key(H[n])!=key(O[n]): div=n; break
    print('%3d %-48s 우리%d 한컴%d 첫 어긋남 쪽 %s'%(i,ms[i]['path'][:48],len(O),len(H),(div+1) if div is not None else '-'))
    if div is not None:
        for nm,d_ in (('한컴',H),('우리',O)):
            prev=lines(d_[div-1]) if div>0 else []; cur=lines(d_[div])
            pb=[(y,t[:14]) for y,t,s in prev if y<790][-2:]; cb=[(y,t[:14]) for y,t,s in cur if y>50][:2]
            print('     ',nm,'쪽',div,'끝',pb,'| 쪽',div+1,'시작',cb)

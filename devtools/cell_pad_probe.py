"""HWP 칸의 '안 여백 지정'(속성 비트 16)이 꺼진 칸(행 하나만 차지·높이 지정 없음)에서 한컴이 저장한 칸 높이 − 글 높이가 표 기본 여백 합과 맞는지 칸 저장 여백 합과 맞는지 센다.
    python devtools/cell_pad_probe.py     (결과 2026-10-15: 표 기본 1,162 대 칸 저장 25 → hwp2html 이 비트가 꺼진 칸은 표 기본 여백을 쓴다)"""
import sys, os, struct, glob, collections
sys.path.insert(0,'.')
import hwp2html as H
st=collections.Counter(); docs=collections.defaultdict(collections.Counter)
def walk(n):
    for ch in getattr(n,'ch',[]):
        yield ch; yield from walk(ch)
for f in sorted(glob.glob('corpus/rhwp*/**/*.hwp',recursive=True)+glob.glob('samples/**/*.hwp',recursive=True)):
    try:
        if open(f,'rb').read(8)!=bytes.fromhex('d0cf11e0a1b11ae1') or os.path.getsize(f)>8_000_000: continue
        H.load(f); root=H.tree(H.records(H.dec(H.c.read('/BodyText/Section0'))))
    except Exception: continue
    for n in walk(root):
        if n.tag==71 and n.p[:4]==b' lbt':
            tbl=next((c for c in n.ch if c.tag==77),None)
            if tbl is None or len(tbl.p)<18: continue
            tmg=struct.unpack_from('<4H',tbl.p,10)
            kids=n.ch
            for idx,c in enumerate(kids):
                if c.tag!=72 or len(c.p)<32: continue
                col,row,cs,rs,w,h=struct.unpack_from('<HHHHII',c.p,8)
                mg=struct.unpack_from('<4H',c.p,24); hm=struct.unpack_from('<I',c.p,4)[0]>>16&1
                if rs!=1 or any(v>=0x8000 for v in mg) or hm: continue
                if mg[2]+mg[3]==tmg[2]+tmg[3]: continue            # 구별 안 되는 칸은 제외
                paras=[]; j=idx+1
                while j<len(kids) and kids[j].tag==66: paras.append(kids[j]); j+=1
                paras+=[x for x in c.ch if x.tag==66]
                tb=H.text_bottom(paras)
                if tb<=0: continue
                d_tbl=h/100-tb-(tmg[2]+tmg[3])/100
                d_cell=h/100-tb-(mg[2]+mg[3])/100
                k=os.path.basename(f)
                if abs(d_tbl)<0.6 and abs(d_cell)>=0.6: st['표 기본 여백과 맞음']+=1; docs[k]['표']+=1
                elif abs(d_cell)<0.6 and abs(d_tbl)>=0.6: st['칸 저장 여백과 맞음']+=1; docs[k]['칸']+=1
                elif abs(d_cell)<0.6 and abs(d_tbl)<0.6: st['둘 다']+=1
                else: st['둘 다 아님(최소 높이 지정 등)']+=1
print(dict(st))
for k,v in sorted(docs.items(), key=lambda kv:-sum(kv[1].values()))[:25]: print(k,dict(v))

"""줄 끊김 재현을 글꼴(한글 칸 글꼴 이름)별로 나눠, 폭 배율을 바꿔 가며 일치율이 가장 높은 배율을 찾는다(글꼴별 폭 오차 진단).
    PYTHONUTF8=1 python devtools/linebreak_fonts.py [최소 줄 수=40]"""
import collections, glob, math, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'devtools')); sys.path.insert(0, str(ROOT / 'core')); sys.path.insert(0, str(ROOT))
import linebreak_eval as L
P, H, M, B = L.P, L.H, L.M, L.B
MIN = int(sys.argv[1]) if len(sys.argv) > 1 else 40
SCALES = (0.96, 0.97, 0.98, 0.99, 1.0, 1.01, 1.02, 1.03, 1.04)
model = L.Model()
data = collections.defaultdict(list)       # 글꼴 -> [(문단 W 목록, 텍스트, ku, 줄 목록)]
for f in sorted(glob.glob(str(ROOT / 'corpus' / 'rhwp*' / '**' / '*.hwp'), recursive=True)):
    if open(f, 'rb').read(8) != L.OLE or os.path.getsize(f) > 8_000_000: continue
    try: ps = [p for p in P.iter_paragraphs(f) if len(p.lines) >= 2]
    except Exception: continue
    for p in ps:
        cs = [H.charshapes[k] for k in p.sid]; sl = L.slots(p.text)
        W = [model.width(c, s, l) for c, s, l in zip(p.text, cs, sl)]
        ku = 1 if p.shape['bw'] else 0; ok = B.break_positions(p.text, ku); items = []
        for k in range(len(p.lines) - 1):
            a, b = L.idx_of(p, p.lines[k]['pos']), L.idx_of(p, p.lines[k + 1]['pos'])
            if b <= a or b >= len(p.text) or '\t' in p.text[a:b]: continue
            items.append((a, B.skip_spaces(p.text, b), L.line_avail(p, k)))
        if items: data[cs[0]['langs'][0]['face']].append((W, p.text, ku, ok, items))
rows = []
for face, paras in data.items():
    n = sum(len(x[4]) for x in paras)
    if n < MIN: continue
    res = {}
    for s in SCALES:
        okc = 0
        for W, text, ku, ok, items in paras:
            Ws = [w * s for w in W]
            for a, truth, av in items:
                if B.skip_spaces(text, B.break_one(text, Ws, a, av, ku, ok)) == truth: okc += 1
        res[s] = okc / n
    best = max(res, key=res.get)
    rows.append((n, face, res[1.0], best, res[best], M.find(face) is not None))
rows.sort(reverse=True)
print('%-16s %6s %8s  %s  %s' % ('글꼴', '줄 수', '배율1.0', '최적 배율', '폭표'))
for n, face, r1, best, rb, hit in rows: print('%-16s %6d %7.1f%%  x%.2f → %.1f%%   %s' % (face[:16], n, 100 * r1, best, 100 * rb, 'rhwp 표 있음' if hit else '표 없음(기본값)'))

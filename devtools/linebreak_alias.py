"""글꼴 이름 → 폭표 대응을 한컴이 저장한 줄 끊김으로 고른다: 한글 칸 글꼴마다 후보 폭표를 바꿔 끼워 가며 일치율을 비교한다.
    PYTHONUTF8=1 python devtools/linebreak_alias.py [최소 줄 수=30]"""
import collections, glob, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'devtools')); sys.path.insert(0, str(ROOT / 'core')); sys.path.insert(0, str(ROOT))
import linebreak_eval as L
P, H, M, B = L.P, L.H, L.M, L.B
MIN = int(sys.argv[1]) if len(sys.argv) > 1 else 30
CAND = ['HCR Batang', 'HCR Dotum', 'Haansoft Batang', 'Haansoft Dotum', 'Batang', 'Dotum', 'Gulim', 'Malgun Gothic', 'HYSinMyeongJo-Medium', 'HYGothic-Medium', 'HumanMyeongJo', 'HanyangSinMyeongJo', 'HanyangJungGothic', 'Times New Roman', 'Arial']
by = collections.defaultdict(list)
for f in sorted(glob.glob(str(ROOT / 'corpus' / 'rhwp*' / '**' / '*.hwp'), recursive=True)):
    if open(f, 'rb').read(8) != L.OLE or os.path.getsize(f) > 8_000_000: continue
    try: ps = [p for p in P.iter_paragraphs(f) if len(p.lines) >= 2]
    except Exception: continue
    for p in ps:
        cs = [H.charshapes[k] for k in p.sid]
        if not cs: continue
        by[cs[0]['langs'][0]['face']].append((p, cs))
def agreement(face, alias, paras):
    old = M.ALIAS.get(face); M.ALIAS[face] = alias
    ok = n = 0; model = L.Model()
    try:
        for p, cs in paras:
            sl = L.slots(p.text); W = [model.width(c, s, l) for c, s, l in zip(p.text, cs, sl)]
            ku = 1 if p.shape['bw'] else 0; okp = B.break_positions(p.text, ku)
            for k in range(len(p.lines) - 1):
                a, b = L.idx_of(p, p.lines[k]['pos']), L.idx_of(p, p.lines[k + 1]['pos'])
                if b <= a or b >= len(p.text) or '\t' in p.text[a:b]: continue
                n += 1; ok += B.skip_spaces(p.text, B.break_one(p.text, W, a, L.line_avail(p, k), ku, okp)) == B.skip_spaces(p.text, b)
    finally:
        if old is None: M.ALIAS.pop(face, None)
        else: M.ALIAS[face] = old
    return ok / n if n else 0, n
print('%-14s %6s %-14s %6s | 후보 상위' % ('글꼴', '줄 수', '현재 대응', '일치'))
for face, paras in sorted(by.items(), key=lambda kv: -len(kv[1])):
    cur = M.ALIAS.get(face, face); r0, n = agreement(face, cur, paras)
    if n < MIN: continue
    res = sorted(((agreement(face, c, paras)[0], c) for c in CAND), reverse=True)[:3]
    print('%-14s %6d %-14s %5.1f%% | %s' % (face[:14], n, cur[:14], 100 * r0, '  '.join('%s %.1f%%' % (c, 100 * r) for r, c in res)))

"""사다리 결과로 글자 폭 계산식 후보를 가린다. python synth_formula.py <사다리이름>   (사다리 json 은 face·unit·size·ratio·spacing·k·w 를 가진다)"""
import sys, json, math, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import hwppara as P, metrics as M
name = sys.argv[1]
spec = json.load((ROOT / 'corpus' / 'synth' / (name + '.json')).open(encoding='utf-8'))
ps = [p for p in P.iter_paragraphs(str(ROOT / 'corpus' / 'synth' / 'out' / (name + '.hwp'))) if p.text.strip()]
assert len(ps) == len(spec), (len(ps), len(spec))
res = collections.defaultdict(list)
for d, p in zip(spec, ps):
    n = sum(1 for q in p.pos if q < p.lines[1]['pos']) // len(d['unit']) if len(p.lines) > 1 else len(p.text) // len(d['unit'])
    res[(d['face'], d['unit'], d['size'], d['ratio'], d['spacing'], d['k'])].append((p.lines[0]['w'], n))
r4 = lambda x: 4 * math.floor(x / 4 + 0.5); f4 = lambda x: 4 * math.floor(x / 4)
F = {
 'round4(adv·size·ratio)': lambda a, s, r: r4(a * s * r),
 'floor4(adv·size·ratio)': lambda a, s, r: f4(a * s * r),
 'floor4(round4(adv·size)·ratio)': lambda a, s, r: f4(r4(a * s) * r),
 'round4(round4(adv·size)·ratio)': lambda a, s, r: r4(r4(a * s) * r),
}
score = {k: 0 for k in F}; tot = 0; bad = collections.defaultdict(list)
for (face, u, size, ratio, sp, k), v in sorted(res.items()):
    if sp: continue
    v.sort()
    lo = max((w for w, n in v if n < k), default=None); hi = min((w for w, n in v if n >= k), default=None)
    if lo is None or hi is None: continue
    c_lo, c_hi = lo / k, hi / k; tot += 1
    a = M.advance(face, u); s = size * 100; r = ratio / 100
    for nm, f in F.items():
        val = f(a, s, r)
        if c_lo - 1e-9 < val <= c_hi + 1e-9: score[nm] += 1
        elif len(bad[nm]) < 6: bad[nm].append((face, u, size, ratio, round(val, 1), (round(c_lo, 2), round(c_hi, 2))))
print('측정 조합', tot)
for nm, v in sorted(score.items(), key=lambda kv: -kv[1]): print('%4d / %d  %s' % (v, tot, nm))
best = max(score, key=score.get); print('최상 식', best, '의 어긋난 예:'); [print('  ', b) for b in bad[best]]

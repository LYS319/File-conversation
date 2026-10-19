"""글자 폭 사다리(V3 1단계 검증): 글자 하나(또는 짧은 낱말)를 반복한 문단을 줄 폭만 조금씩 바꿔 늘어놓고, 한컴이 첫 줄에 몇 개까지 넣는지 본다.
첫 줄 개수가 k 에서 k+1 로 바뀌는 줄 폭 = (k+1)×글자 폭 이므로 글자 폭을 (줄 폭 간격/k)의 정밀도로 안다.
    python synth_ladder.py build  <이름> [--faces 글꼴,글꼴] [--units 가|0|a] [--k 20] [--step 20] [--span 400] [--size 10] [--ratio 100] [--spacing 0]   → corpus/synth/<이름>.hwpx/.json
    (한컴으로 열어 저장: python devtools/hancom_pdf.py --out corpus/synth/out --as hwp corpus/synth/<이름>.hwpx)
    python synth_ladder.py analyze <이름>       → 글꼴×글자 별 한컴 글자 폭 구간과 우리 모델 폭의 차이
"""
import argparse, collections, json, math, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'devtools'))
from synth_hwpx import build, TEXT_W
OUT = ROOT / 'corpus' / 'synth'
FACES = '함초롬바탕,함초롬돋움,맑은 고딕,바탕,굴림,돋움,한컴바탕,휴먼명조'
UNITS = '가|0|a|W|.|,|:|('


def cmd_build(a):
    from core import metrics as M
    faces = a.faces.split(','); units = [u for u in a.units.split('|') if u]
    rows = []
    sizes = [float(x) for x in a.sizes.split(',')] if a.sizes else [a.size]
    for face in faces:
        for sz in sizes:
            for u in units:
                e = sum(M.advance(face, c) for c in u) * sz * 100 * a.ratio / 100 * (1 + a.spacing / 100)      # 우리 폭 추정(한 단위, HWPUNIT)
                for d in range(-a.span, a.span + 1, a.step):
                    w = int(round(a.k * e + d))
                    if not 3000 <= w <= TEXT_W: continue
                    rows.append(dict(text=u * (a.k + 12), face=face, size=sz, ratio=a.ratio, spacing=a.spacing, ku=1, right=TEXT_W - w, unit=u, k=a.k, w=w, est=e, name='%s|%s|%d' % (face, u, w)))
    OUT.mkdir(parents=True, exist_ok=True)
    build(rows, str(OUT / (a.name + '.hwpx'))); (OUT / (a.name + '.json')).write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    print('문단 %d개 → %s' % (len(rows), OUT / (a.name + '.hwpx')))


def cmd_analyze(a):
    from core import hwppara as P
    spec = json.load((OUT / (a.name + '.json')).open(encoding='utf-8'))
    ps = [p for p in P.iter_paragraphs(str(OUT / 'out' / (a.name + '.hwp'))) if p.text.strip()]
    assert len(ps) == len(spec), (len(ps), len(spec))
    res = collections.defaultdict(list)       # (글꼴, 단위, k) -> [(폭, 첫 줄 개수)]
    for d, p in zip(spec, ps):
        n = len(p.text.replace(' ', '')) if len(p.lines) < 2 else sum(1 for q in p.pos if q < p.lines[1]['pos'])
        res[(d['face'], d['unit'], d['k'], d['size'], d['ratio'], d['spacing'])].append((p.lines[0]['w'], n // max(1, len(d['unit'])), d['est']))
    print('%-12s %-4s | 한컴 한 단위 폭 구간(HWPUNIT) | 우리 모델 | 차이' % ('글꼴', '단위'))
    for (face, u, k, sz, ra, sp), v in sorted(res.items()):
        v.sort()
        lo = max((w for w, n, _ in v if n < k), default=None); hi = min((w for w, n, _ in v if n >= k), default=None)
        est = v[0][2]
        if lo is None or hi is None: print('%-12s %-4s %4g 장평%d 자간%d | 구간 밖(첫 줄 개수 %s~%s)' % (face, u, sz, ra, sp, v[0][1], v[-1][1])); continue
        c_lo, c_hi = lo / k, hi / k      # n>=k 가 되는 가장 작은 폭 hi 이하, lo 초과 → 한 단위 폭 ∈ (lo/k, hi/k]
        print('%-12s %-4s %4g 장평%3d 자간%3d | %8.2f ~ %8.2f | %8.1f | %+.2f' % (face, repr(u)[1:-1], sz, ra, sp, c_lo, c_hi, est, (c_lo + c_hi) / 2 - est))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest='cmd', required=True)
    b = sp.add_parser('build'); b.add_argument('name'); b.add_argument('--faces', default=FACES); b.add_argument('--units', default=UNITS)
    for k_, v_ in (('k', 20), ('step', 20), ('span', 400), ('size', 10), ('ratio', 100), ('spacing', 0)): b.add_argument('--' + k_, type=int, default=v_)
    b.add_argument('--sizes', default='')
    x = sp.add_parser('analyze'); x.add_argument('name')
    a = ap.parse_args()
    {'build': cmd_build, 'analyze': cmd_analyze}[a.cmd](a)

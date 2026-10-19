"""문장부호 폭 실측(V3 1단계): 폭표 값이 의심스러운 (글꼴, 문장부호) 쌍을 한컴 합성 사다리로 잰다.
단위 = '가'+부호 를 k 번 반복한 문단(부호가 줄 머리에 못 오는 금칙이라도 쌍 단위로 안 끊김)을 줄 폭만 바꿔 늘어놓고, 한컴이 첫 줄에 k 쌍을 넣는 최소 줄 폭 = k×(가 폭 + 부호 폭).
'가' 폭은 같은 글꼴의 '가' 사다리로 따로 잰다.
    python devtools/synth_punct.py build  <이름>          → corpus/synth/<이름>.hwpx/.json
    python devtools/hancom_pdf.py --out corpus/synth/out --as hwp corpus/synth/<이름>.hwpx
    python devtools/synth_punct.py analyze <이름>        → 글꼴×부호별 한컴 폭(em)과 폭표 값
"""
import collections, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'devtools'))
from synth_hwpx import build, TEXT_W
OUT = ROOT / 'corpus' / 'synth'
K = 20; SIZE = 10
# punct_scan.py 가 고른 의심 쌍(2026-10-14) + 대조용(값이 믿을 만한 쌍)
PAIRS = {'굴림체': '·※%@', '돋움체': '·※', '한양중고딕': '·•※–', '한양신명조': '·•※–', 'HY중고딕': '-·', 'HY헤드라인M': '·※', '휴먼명조': '·•※', '휴먼고딕': '·',
         '함초롬돋움': '·※', '함초롬바탕': '·※', '돋움': '·※', '맑은 고딕': '·※', '한컴돋움': '·※'}


def cmd_build(a):
    rows = []
    for face, cs in PAIRS.items():
        for u in ['가'] + ['가' + c for c in cs]:
            lo, hi = (18000, 22000) if u == '가' else (22000, 42000)      # 한 단위 폭 0.9~1.1em(가) / 1.1~2.1em(가+부호), 크기 10pt = 1em 1000 HWPUNIT
            step = 40 if u == '가' else 120
            for w in range(lo, hi + 1, step):
                if w > TEXT_W: continue
                rows.append(dict(text=u * (K + 12), face=face, size=SIZE, ratio=100, spacing=0, ku=1, right=TEXT_W - w, unit=u, k=K, w=w, est=0, name='%s|%s|%d' % (face, u, w)))
    OUT.mkdir(parents=True, exist_ok=True)
    build(rows, str(OUT / (a.name + '.hwpx'))); (OUT / (a.name + '.json')).write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    print('문단 %d개 → %s' % (len(rows), OUT / (a.name + '.hwpx')))


def cmd_analyze(a):
    from core import hwppara as P, metrics as M
    spec = json.load((OUT / (a.name + '.json')).open(encoding='utf-8'))
    ps = [p for p in P.iter_paragraphs(str(OUT / 'out' / (a.name + '.hwp'))) if p.text.strip()]
    assert len(ps) == len(spec), (len(ps), len(spec))
    res = collections.defaultdict(list)
    for d, p in zip(spec, ps):
        n = len(p.text) if len(p.lines) < 2 else sum(1 for q in p.pos if q < p.lines[1]['pos'])
        res[(d['face'], d['unit'])].append((p.lines[0]['w'], n // len(d['unit'])))
    unit_w = {}
    for (face, u), v in res.items():
        lo = max((w for w, n in v if n < K), default=None); hi = min((w for w, n in v if n >= K), default=None)
        unit_w[(face, u)] = None if lo is None or hi is None else ((lo + hi) / 2 / K, (hi - lo) / K)
    print('%-12s %-3s | 한컴 폭(em) ±구간 | 폭표(em) | 차이' % ('글꼴', '부호'))
    for (face, u), v in sorted(unit_w.items()):
        if u == '가': continue
        g, pw = unit_w.get((face, '가')), v
        if g is None or pw is None: print('%-12s %-3s | 구간 밖(가 %s, 쌍 %s)' % (face, u[1:], g, pw)); continue
        em = SIZE * 100; w = (pw[0] - g[0]) / em; tol = (pw[1] + g[1]) / em; t = M.advance(face, u[1:])
        print('%-12s %-3s | %.3f ±%.3f | %.2f | %+.3f%s' % (face, u[1:], w, tol / 2, t, w - t, '  ←' if abs(w - t) > 0.1 else ''))


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest='cmd', required=True)
    for n_, f_ in (('build', cmd_build), ('analyze', cmd_analyze)): sp.add_parser(n_).add_argument('name')
    a = ap.parse_args(); {'build': cmd_build, 'analyze': cmd_analyze}[a.cmd](a)

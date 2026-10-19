"""실제 문장 합성 시험: 공개 말뭉치(corpus/rhwp*)의 문단 글에 글꼴·크기·장평·자간·줄 나눔 기준·줄 폭을 무작위로 조합한 합성 HWPX 를 만든다. 한컴이 줄을 끊은 결과(정답)와 비교한다.
    python synth_text.py build <이름> [--n 600] [--seed 1] [--ku0 0.5]    → corpus/synth/<이름>.hwpx/.json
    (한컴으로: hancom_pdf.py --out corpus/synth/out --as hwp corpus/synth/<이름>.hwpx)
    python synth_text.py check <이름>        → 조건별 일치율과 어긋난 문단 예"""
import argparse, collections, glob, json, os, random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'devtools'))
from synth_hwpx import build, TEXT_W
OUT = ROOT / 'corpus' / 'synth'
FACES = ['함초롬바탕', '맑은 고딕', '바탕', '굴림', '함초롬돋움', '휴먼명조', '돋움']
OLE = bytes.fromhex('D0CF11E0A1B11AE1')


def corpus_texts(limit=4000):
    from core import hwppara as P
    out = []
    for f in sorted(glob.glob(str(ROOT / 'corpus' / 'rhwp*' / '**' / '*.hwp'), recursive=True)):
        if open(f, 'rb').read(8) != OLE or os.path.getsize(f) > 3_000_000 or '사내' in f: continue
        try:
            for p in P.iter_paragraphs(f):
                t = p.text.replace('\u00a0', ' ').strip()
                if 60 <= len(t) <= 500 and '\t' not in t and '\n' not in t and not any(c in t for c in '\u2007\u2060'): out.append(t)
        except Exception: pass
        if len(out) >= limit: break
    return out


def cmd_build(a):
    rnd = random.Random(a.seed); texts = corpus_texts(); rnd.shuffle(texts)
    rows = []
    for t in texts[:a.n]:
        ku = 0 if rnd.random() < a.ku0 else 1
        rows.append(dict(text=t, face=rnd.choice(FACES), size=rnd.choice([9, 10, 10, 10.5, 11, 12, 13]), ratio=rnd.choice([100, 100, 100, 95, 90]), spacing=rnd.choice([0, 0, 0, -3, -5]),
                         ku=ku, right=TEXT_W - rnd.randrange(14000, 42000, 4), condense=rnd.choice([0, 0, 0, 0, 25, 50, 75]) if a.condense else 0))
    OUT.mkdir(parents=True, exist_ok=True)
    build(rows, str(OUT / (a.name + '.hwpx'))); (OUT / (a.name + '.json')).write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    print('문단 %d개 → %s' % (len(rows), OUT / (a.name + '.hwpx')))


def cmd_check(a):
    from core import hwppara as P, linebreak as B
    from core.widthmodel import Model, slots, widths
    H = P.H; m = Model()
    spec = json.load((OUT / (a.name + '.json')).open(encoding='utf-8'))
    ps = [p for p in P.iter_paragraphs(str(OUT / 'out' / (a.name + '.hwp'))) if p.text.strip()]
    assert len(ps) == len(spec), (len(ps), len(spec))
    tally = collections.defaultdict(lambda: [0, 0]); bad = []
    for d, p in zip(spec, ps):
        cs = [H.charshapes[i] for i in p.sid]; W, T = widths(m, p.text, cs)
        ku = 1 if p.shape['bw'] else 0; ok = B.break_positions(p.text, ku)
        hs = [B.skip_spaces(p.text, next((i for i, q in enumerate(p.pos) if q >= l['pos']), len(p.text))) for l in p.lines[1:]]
        ours = []; i = 0
        while i < len(p.text):
            j = B.skip_spaces(p.text, B.break_one(p.text, W, i, p.lines[0]['w'], ku, ok, T=T, cond=(p.shape['prop'] >> 9) & 0x7f))
            if j >= len(p.text): break
            ours.append(j); i = j
        same = ours == hs
        # 줄 단위 일치(앞 줄은 한컴 시작에서 다시 시작)
        starts = [0] + hs; n_lines = len(hs); lm = 0
        for k, s0 in enumerate(starts[:-1] if n_lines else []):
            j = B.skip_spaces(p.text, B.break_one(p.text, W, s0, p.lines[0]['w'], ku, ok, T=T, cond=(p.shape['prop'] >> 9) & 0x7f)); lm += j == starts[k + 1]
        for key in (('전체',), ('ku', ku), ('글꼴', d['face']), ('자간', d['spacing']), ('장평', d['ratio']), ('압축', d['condense'])):
            tally[key][0] += same; tally[key][1] += 1
        tally[('줄 단위', ku)][0] += lm; tally[('줄 단위', ku)][1] += n_lines
        if not same: bad.append((d, p, hs, ours))
    for k, (ok_, n) in sorted(tally.items(), key=lambda kv: str(kv[0])): print('%-22s %4d / %4d  (%.1f%%)' % (k, ok_, n, 100 * ok_ / max(1, n)))
    for d, p, hs, ours in bad[:a.show]:
        k = next((i for i, (x, y) in enumerate(zip(hs, ours)) if x != y), min(len(hs), len(ours)))
        h = hs[k] if k < len(hs) else None; o = ours[k] if k < len(ours) else None
        print('✗ ku=%d %s %spt 장평%d 자간%d 폭%d 압축%d | 첫 어긋남 줄 %d: 한컴 %s %r | 우리 %s %r' % (1 if p.shape['bw'] else 0, d['face'], d['size'], d['ratio'], d['spacing'], p.lines[0]['w'], d['condense'], k + 1, h, p.text[h-8:h+6] if h else '', o, p.text[o-8:o+6] if o else ''))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest='cmd', required=True)
    b = sp.add_parser('build'); b.add_argument('name'); b.add_argument('--n', type=int, default=600); b.add_argument('--seed', type=int, default=1); b.add_argument('--ku0', type=float, default=0.5); b.add_argument('--condense', action='store_true')
    c = sp.add_parser('check'); c.add_argument('name'); c.add_argument('--show', type=int, default=12)
    a = ap.parse_args(); {'build': cmd_build, 'check': cmd_check}[a.cmd](a)

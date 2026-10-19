"""줄 끊김 재현 시험(V3 1단계): 한컴이 저장한 줄 끊김(PARA_LINE_SEG)을 정답으로, core/linebreak.py 가 같은 자리에서 줄을 끊는지 잰다.
각 저장된 줄 k(마지막 줄 제외)의 시작 글자에서 우리 줄 나눔기를 한 줄만 돌려 '다음 줄 시작'이 저장된 값과 같은지 본다(앞 줄 오차가 뒤로 번지지 않게 줄마다 저장된 시작에서 다시 시작).
    PYTHONUTF8=1 python devtools/linebreak_eval.py [--docs 이름…] [--examples N] [--space half|font] [--noquant]
글자 폭 모델은 rhwp 와 같은 식: 폭 = floor(폭표 em × 글자 크기×상대크기) × 장평 + 자간×(폭/글자 크기) (자간 음수면 폭×장평의 절반이 하한). 공백은 0.5em(글꼴 자체 공백을 쓰는 글자 모양은 폭표의 공백).
이전의 '여유' 분석은 linebreak_slack.py.
"""
import argparse, collections, glob, math, os, random, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import hwppara as P, metrics as M, linebreak as B
from core.widthmodel import slots, Model, widths
H = P.H
OLE = bytes.fromhex('D0CF11E0A1B11AE1')
FACE = os.environ.get('FACE')      # 예시를 이 한글 칸 글꼴로만 거른다


def idx_of(p, chpos):
    lo, hi = 0, len(p.pos)
    while lo < hi:
        m = (lo + hi) // 2
        if p.pos[m] < chpos: lo = m + 1
        else: hi = m
    return lo


def line_avail(p, k):
    ind = p.shape['indent'] / 2      # 문단 모양 들여쓰기는 HWPUNIT×2 로 저장
    return p.lines[k]['w'] - (max(ind, 0) if k == 0 else max(-ind, 0))


def check_para(p, model, tally, examples, want_ex):
    n = len(p.lines)
    cs = [H.charshapes[k] for k in p.sid]
    sl = slots(p.text)
    W, T = widths(model, p.text, cs)
    ku = 1 if p.shape['bw'] else 0
    ok = B.break_positions(p.text, ku)
    for k in range(n - 1):
        a = idx_of(p, p.lines[k]['pos']); b = idx_of(p, p.lines[k + 1]['pos'])
        if b <= a or b >= len(p.text): continue
        if '\t' in p.text[a:b]: tally['건너뜀(탭)'] += 1; continue
        pred = B.skip_spaces(p.text, B.break_one(p.text, W, a, line_avail(p, k), ku, ok, T=T, cond=(p.shape['prop'] >> 9) & 0x7f))
        truth = B.skip_spaces(p.text, b)
        key = 'ok' if pred == truth else 'early' if pred < truth else 'late'
        tally[key] += 1
        tally['ku=%d %s' % (ku, key)] += 1
        if key != 'ok' and want_ex and len(examples) < 4000 and (not FACE or cs[a]['langs'][0]['face'] == FACE):
            examples.append((key, p.text[max(a, truth - 14):truth], p.text[truth:truth + 8], p.text[max(a, pred - 14):pred], int(line_avail(p, k)), int(sum(W[a:truth])), ku, cs[a]['langs'][0]['face'], k, n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--docs', nargs='*', default=[]); ap.add_argument('--examples', type=int, default=0)
    ap.add_argument('--space', default='half'); ap.add_argument('--noquant', action='store_true')
    a = ap.parse_args()
    files = []
    for pat in ('corpus/rhwp/**/*.hwp', 'corpus/rhwp2/**/*.hwp', 'corpus/*.hwp', 'samples/**/*.hwp'):
        files += glob.glob(str(ROOT / pat), recursive=True)
    files = sorted({os.path.abspath(f) for f in files})
    model = Model(a.space, not a.noquant); tot = collections.Counter(); per = []; ex = []
    for f in files:
        if a.docs and not any(d in f for d in a.docs): continue
        if open(f, 'rb').read(8) != OLE or os.path.getsize(f) > 8_000_000: continue
        try: ps = [p for p in P.iter_paragraphs(f) if len(p.lines) >= 2]
        except Exception: continue
        t = collections.Counter()
        for p in ps: check_para(p, model, t, ex, a.examples)
        tot.update(t)
        n = t['ok'] + t['early'] + t['late']
        if n: per.append((os.path.basename(f), n, t['ok'] / n))
    n = tot['ok'] + tot['early'] + tot['late']
    print('줄 %d개 (문서 %d건) — 정확히 일치 %.1f%%  우리가 일찍 끊음 %.1f%%  우리가 늦게 끊음 %.1f%%' % (n, len(per), 100 * tot['ok'] / n, 100 * tot['early'] / n, 100 * tot['late'] / n))
    for ku in (0, 1):
        m = tot['ku=%d ok' % ku] + tot['ku=%d early' % ku] + tot['ku=%d late' % ku]
        if m: print('  한글 줄 나눔 %s: 줄 %d  일치 %.1f%%  일찍 %.1f%%  늦게 %.1f%%' % ('글자 단위' if ku else '어절 단위', m, 100 * tot['ku=%d ok' % ku] / m, 100 * tot['ku=%d early' % ku] / m, 100 * tot['ku=%d late' % ku] / m))
    per.sort(key=lambda x: x[2]); print('일치율 낮은 문서(줄 20개 이상):', [(a_, b_, round(c_, 2)) for a_, b_, c_ in per if b_ >= 20][:8])
    if a.examples:
        random.seed(1); random.shuffle(ex)
        for e in ex[:a.examples]: print(e)


if __name__ == '__main__': main()

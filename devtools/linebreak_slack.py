"""줄 끊김 재현 시험(V3 1단계): 한컴이 저장한 줄 끊김(PARA_LINE_SEG)을 정답으로, 우리 글자 폭 모델이 각 줄을 '한컴과 같은 자리'에서 끊을 수 있는지 잰다.
줄 k(마지막 줄 제외)마다 두 조건: ① 줄 글이 줄 폭에 들어간다(우리 폭 W ≤ 줄 폭) ② 다음 낱말을 붙이면 넘친다(W + 공백 + 다음 낱말 > 줄 폭).
둘 다 맞으면 '일치', ①이 틀리면 '우리가 넓게 잼'(한컴은 들어가는데 우리는 안 들어감), ②가 틀리면 '우리가 좁게 잼'(한컴은 넘치는데 우리는 더 들어감). 여유 분포(줄 폭 − W, 글자 폭 단위)도 낸다.
    PYTHONUTF8=1 python devtools/linebreak_slack.py [--space half|font] [--spacing none|em|glyph] [--max N] [--docs 부분이름 …]
"""
import argparse, collections, glob, os, statistics as st, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'core'))
import hwppara as P, metrics as M
H = P.H
OLE = bytes.fromhex('D0CF11E0A1B11AE1')


class Model:
    """글자 폭(HWPUNIT) = 폭표(em) × 글자 크기(HWPUNIT) × 장평 + 자간. 변형은 옵션으로 바꿔 가며 시험한다."""
    def __init__(s, space='half', spacing='glyph', cb='bw', indent='sub'): s.space, s.spacing, s.cb, s.indent = space, spacing, cb, indent

    def sub(s, p, k):
        """줄 k 에서 저장된 줄 폭에서 더 빼야 하는 들여쓰기(HWPUNIT). 문단 모양의 들여쓰기 값은 HWPUNIT×2 로 저장돼 있다."""
        if s.indent == 'none': return 0
        ind = p.shape['indent'] / 2
        return max(ind, 0) if k == 0 else max(-ind, 0)

    def width(s, ch, cs):
        lang = H.lang_of(ch)
        L = cs['langs'][lang if lang is not None else 0]
        size = cs['size'] * 100 * L['rel'] / 100        # pt -> HWPUNIT(1pt = 100)
        face = L['face']
        if ch == ' ' or ch == ' ':
            base = 0.5 if s.space == 'half' and not cs['ufs'] else M.advance(face, ' ', cs['bold'], cs['italic'])
        elif ch == '\t': base = 0.0
        else: base = M.advance(face, ch, cs['bold'], cs['italic'])
        w = base * size * L['ratio'] / 100
        sp = L['spacing']
        if s.spacing == 'em': w += sp / 100 * size
        elif s.spacing == 'glyph': w += sp / 100 * size * (1.0 if base > 0.75 else 0.5)      # 자간은 글자 폭의 %: 전각 1em·반각 0.5em 기준(잠정)
        return w


def idx_of(p, chpos):
    """chpos(PARA_TEXT 글자 위치) -> 글자 색인(그 위치 이상인 첫 글자)."""
    lo, hi = 0, len(p.pos)
    while lo < hi:
        m = (lo + hi) // 2
        if p.pos[m] < chpos: lo = m + 1
        else: hi = m
    return lo


def word_end(text, i, char_break):
    """i 에서 시작하는 '다음 낱말' 끝(공백 직전). 글자 단위 줄 나눔 문단의 한글은 글자 한 개."""
    if char_break and i < len(text) and H.lang_of(text[i]) == 0: return i + 1
    j = i
    while j < len(text) and text[j] not in ' \t\n': j += 1
    return max(j, i + 1)


def eval_para(p, model, tally, slack):
    n = len(p.lines)
    cs = [H.charshapes[k] for k in p.sid]
    W = [model.width(c, s) for c, s in zip(p.text, cs)]
    char_break = {'bw': bool(p.shape['bw']), 'flip': not p.shape['bw'], 'never': False, 'always': True}[model.cb]
    for k in range(n - 1):
        a, b = idx_of(p, p.lines[k]['pos']), idx_of(p, p.lines[k + 1]['pos'])
        if b <= a or b >= len(p.text): continue
        seg = p.text[a:b]
        if '\n' in seg[:-1] or '\t' in seg: tally['건너뜀(탭·줄바꿈)'] += 1; continue
        e = len(seg.rstrip(' ')) + a        # 줄 끝 공백은 줄 폭에 안 센다
        line_w = sum(W[a:e]); avail = p.lines[k]['w'] - model.sub(p, k)
        j = e
        while j < len(p.text) and p.text[j] == ' ': j += 1      # 줄 끝 공백 건너뛰어 다음 낱말 머리
        nw = word_end(p.text, j, char_break)
        over = line_w + sum(W[e:j]) + sum(W[j:nw])      # 다음 낱말을 붙인 폭(사이 공백 포함)
        fit_ok = line_w <= avail + 1; next_over = over > avail - 1
        key = 'ok' if fit_ok and next_over else 'wide' if not fit_ok else 'narrow'
        tally[key] += 1
        slack.append((avail - line_w) / max(1.0, st.mean(W[a:e]) if e > a else 1.0))
    return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--space', default='half'); ap.add_argument('--spacing', default='glyph'); ap.add_argument('--cb', default='bw'); ap.add_argument('--indent', default='sub')
    ap.add_argument('--max', type=int, default=0); ap.add_argument('--docs', nargs='*', default=[])
    a = ap.parse_args()
    files = []
    for pat in ('corpus/rhwp/**/*.hwp', 'corpus/rhwp2/**/*.hwp', 'corpus/*.hwp', 'samples/**/*.hwp', 'corpus/rhwp/**/*.hwpx', 'corpus/rhwp2/**/*.hwpx'):
        files += glob.glob(str(ROOT / pat), recursive=True)
    files = sorted({os.path.abspath(f) for f in files})
    model = Model(a.space, a.spacing, a.cb, a.indent); tot = collections.Counter(); per = []; slack = []
    for f in files:
        if a.docs and not any(d in f for d in a.docs): continue
        if open(f, 'rb').read(8) != OLE or os.path.getsize(f) > 8_000_000: continue
        try: ps = [p for p in P.iter_paragraphs(f) if len(p.lines) >= 2]
        except Exception: continue
        t = collections.Counter(); sl = []
        for p in ps:
            eval_para(p, model, t, sl)
        slack += sl; tot.update(t)
        n = t['ok'] + t['wide'] + t['narrow']
        if n: per.append((os.path.basename(f), n, t['ok'] / n, t['wide'] / n, t['narrow'] / n))
    n = tot['ok'] + tot['wide'] + tot['narrow']
    print('줄 %d개 (문서 %d건) — 일치 %.1f%%  우리가 넓게 잼 %.1f%%  우리가 좁게 잼 %.1f%%   [%s]' % (n, len(per), 100 * tot['ok'] / n, 100 * tot['wide'] / n, 100 * tot['narrow'] / n, dict(tot)))
    if slack:
        q = sorted(slack); print('여유(줄 폭 − 우리 폭, 글자 폭 단위) 중앙값 %.2f  25%% %.2f  75%% %.2f  (정답이면 0 이상, 다음 낱말 폭 안쪽)' % (st.median(q), q[len(q) // 4], q[3 * len(q) // 4]))
    per.sort(key=lambda x: x[2])
    print('일치율 낮은 문서:', [(a, b, round(c, 2)) for a, b, c, _, _ in per[:8]])


if __name__ == '__main__': main()

"""합성 시험 문서 확인: 한컴이 저장한 HWP 의 줄 정보(정답)를 우리 줄 나눔기와 문단마다 비교한다.
    python devtools/synth_check.py <한컴이 저장한 .hwp> [<만든 spec .json>]
spec json 이 있으면 문단별 설명(글꼴·폭 등)을 함께 찍는다. 한컴이 줄을 새로 계산했는지(줄이 2개 이상 문단이 있는지)도 보고한다."""
import json, math, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import hwppara as P, linebreak as B
from core.widthmodel import Model, slots, widths
H = P.H


def first_line_chars(p):
    """한컴이 저장한 첫 줄 글자 수(공백 제외)와 둘째 줄 시작 위치."""
    if len(p.lines) < 2: return len(p.text), None
    b = 0
    while b < len(p.pos) and p.pos[b] < p.lines[1]['pos']: b += 1
    return len(p.text[:b].replace(' ', '')), b


def main():
    hwp = sys.argv[1]; spec = json.load(open(sys.argv[2], encoding='utf-8')) if len(sys.argv) > 2 else None
    ps = [p for p in P.iter_paragraphs(hwp) if p.text.strip()]
    print('한컴이 저장한 문단', len(ps), '/ 줄이 둘 이상인 문단', sum(len(p.lines) >= 2 for p in ps), '/ 저장된 줄 폭 값', sorted({l['w'] for p in ps for l in p.lines})[:6])
    m = Model(); ok = n = 0
    for k, p in enumerate(ps):
        cs = [H.charshapes[i] for i in p.sid]; W, T = widths(m, p.text, cs)
        ku = 1 if p.shape['bw'] else 0; okp = B.break_positions(p.text, ku)
        hs = [B.skip_spaces(p.text, next((i for i, q in enumerate(p.pos) if q >= l['pos']), len(p.text))) for l in p.lines[1:]]
        i = 0; ours = []; kk = 0; ind = p.shape['indent'] / 2
        while i < len(p.text):
            av = p.lines[0]['w'] - (max(ind, 0) if kk == 0 else max(-ind, 0))
            j = B.skip_spaces(p.text, B.break_one(p.text, W, i, av, ku, okp, T=T, cond=(p.shape['prop'] >> 9) & 0x7f))
            if j >= len(p.text): break
            ours.append(j); i = j; kk += 1
        same = ours == hs; ok += same; n += 1
        if not same or k < 3:
            d = spec[k] if spec and k < len(spec) else {}
            print('%s 문단 %d ku=%d 폭 %s | 한컴 줄 시작 %s | 우리 %s | %s' % ('✓' if same else '✗', k, ku, p.lines[0]['w'], hs[:8], ours[:8], {x: d[x] for x in ('face', 'size', 'ratio', 'spacing') if x in d}))
    print('줄 끊김 전체 일치 문단 %d / %d' % (ok, n))


if __name__ == '__main__': main()

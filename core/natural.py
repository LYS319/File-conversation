"""저장된 줄이 없는 문단의 줄 끊김을 우리가 계산한다(V3 1단계 연결부). 변환기(hwp2html·hwpx2html)가 문단 글·글자 모양·문단 모양·줄 폭을 주면 줄이 시작하는 글자 위치 집합을 돌려준다.
한컴이 저장한 줄이 있으면 그것이 항상 우선이고(devtools/linebreak_eval.py: 우리 줄 나눔기는 저장된 8,484줄의 약 90% 를 재현), 이 모듈은 저장된 줄이 없거나 믿을 수 없을 때만 쓴다.
"""
from . import linebreak as B
from .widthmodel import Model, slots, widths

_MODEL = Model()
MAX_CHARS = 20000      # 상한: 한 문단이 이보다 길면 CSS 줄 나눔에 맡긴다(시간 방어)


def natural_breaks(chars, style_of, bw, indent2, avail_hu, model=None, prefix='', hang_em=None, cond=0):
    """chars: [(PARA_TEXT 글자 위치, 글자)], style_of(위치) → 글자 모양(hwp2html.charshapes 항목), bw: 문단 모양 비트 7(1 글자 단위·0 어절 단위),
    indent2: 문단 모양 들여쓰기(HWPUNIT×2 저장값), avail_hu: 줄 폭(HWPUNIT, 문단 좌우 여백을 뺀 것).
    prefix: 번호·글머리표 글(예 '1. '); cond: 문단 모양의 공백 압축 값(%, HWP 비트 9~15 / HWPX condense); hang_em: 자동 내어쓰기면 글이 번호 폭 + hang_em×글자 크기만큼 안쪽에서 시작(모든 줄), 아니면 None(접두가 첫 줄 글 앞에 붙음).
    돌려주는 값: 둘째 줄부터 줄이 시작하는 글자 위치의 집합. 줄바꿈 글자·탭이 있으면 None(CSS 에 맡김)."""
    if any(len(c) != 1 for _, c in chars): return None      # 옛한글 낱자 묶음('ᄒᆞᆫ' 등)은 글자 하나가 여러 글자 — 폭 목록 길이가 글과 어긋나므로 CSS 에 맡김
    text = ''.join(c for _, c in chars)
    if not text or len(text) > MAX_CHARS or '\n' in text or '\t' in text or avail_hu <= 0: return None
    model = model or _MODEL
    pos = [p for p, _ in chars]
    cs = [style_of(p) for p in pos]
    npre = 0
    if prefix:
        first = cs[0]; pre = prefix.strip() if hang_em is not None else prefix
        pw = sum(model.width(c, first, l) for c, l in zip(pre, slots(pre)))
        if hang_em is not None: avail_hu -= pw + hang_em * first['size'] * 100      # 글 칸은 번호 + 본문과의 거리만큼 안쪽(모든 줄)
        else: text = pre + text; pos = [-(len(pre) - i) for i in range(len(pre))] + pos; cs = [first] * len(pre) + cs; npre = len(pre)
        if avail_hu <= 0: return None
    W, T = widths(model, text, cs)
    ku = 1 if bw else 0
    ok = B.break_positions(text, ku)
    ind = indent2 / 2
    out = set(); i = 0; k = 0; n = len(text)
    while i < n:
        av = avail_hu - (max(ind, 0) if k == 0 else max(-ind, 0))
        j = B.skip_spaces(text, B.break_one(text, W, i, av, ku, ok, T=T, cond=cond))
        if j >= n: break
        if j > npre: out.add(pos[j])
        i = j; k += 1
    return out

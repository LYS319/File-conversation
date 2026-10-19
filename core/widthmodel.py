"""글자 폭 모델(V3 1단계): 글자 한 개의 폭(HWPUNIT)을 rhwp 와 같은 식으로 계산한다. 폭표 조회는 metrics.py.
폭 = floor(폭표 em × 글자 크기×언어 칸 상대 크기) × 장평 + 자간×(폭/글자 크기)  (자간 음수면 폭×장평의 절반이 하한). 공백은 0.5em(글꼴 자체 공백을 쓰는 글자 모양은 폭표의 공백).
언어 칸(0 한글·1 영어·2 한자·3 일어·5 기호)은 글자마다 정하고, 공백·ASCII 문장부호·라틴1 부호는 앞 글자의 칸을 따른다(rhwp is_lang_neutral)."""
import math
from . import metrics as M

NEUTRAL_LATIN1 = set(range(0xA0, 0xC0))


def slots(text):
    import hwp2html as H      # 순환 import 를 피해 호출할 때 불러온다(hwp2html 이 core.natural 을 부른다)
    """글자마다 언어 칸(0 한글·1 영어·2 한자·3 일어·5 기호). 공백·ASCII 문장부호·라틴1 부호는 앞 글자의 칸을 따른다(rhwp is_lang_neutral)."""
    out = []; prev = 0
    for ch in text:
        o = ord(ch)
        if ch == ' ' or (o < 0x80 and not ch.isalnum()) or o in NEUTRAL_LATIN1: out.append(prev); continue
        k = H.lang_of(ch)
        prev = 0 if k in (None, 4) else k
        out.append(prev)
    return out


class Model:
    """글자 폭(HWPUNIT). 한컴 오토메이션으로 만든 합성 사다리 문서(devtools/synth_ladder.py, 2026-10-14)로 확정한 식:
    q = 장평 100 이면 4×반올림(폭×크기/4), 100 미만이면 4×내림(폭×크기×장평/4)   (폭 = 글꼴 폭 em × 글자 크기×언어 칸 상대 크기, 4 HWPUNIT 단위로 양자화)
    c = 자간이 있으면 4×(q×(1+자간/100)/4 를 반올림, 정확히 .5 면 내림), 없으면 q
    줄의 마지막 글자는 자간 없이 q 로 센다(장평·자간 사다리의 절편). 공백은 0.5em, 글꼴 자체 공백을 쓰는 글자 모양은 폭표의 공백."""
    def __init__(s, space='half', quant=True): s.space, s.quant = space, quant

    def width2(s, ch, cs, lang):
        """(c, q): 줄 가운데에서의 폭 c 와 줄 끝(자간 뺀) 폭 q."""
        L = cs['langs'][lang]
        size = cs['size'] * 100                      # 글자 크기(HWPUNIT, 1pt = 100)
        fs = size * L['rel'] / 100                   # 언어 칸 상대 크기를 적용한 글자 크기
        face = L['face']
        if ch in '  ':
            adv = 0.5 if s.space == 'half' and not cs['ufs'] else M.advance(face, ' ', cs['bold'], cs['italic'])
        else: adv = M.advance(face, ch, cs['bold'], cs['italic'])
        r = L['ratio'] / 100
        b = adv * fs
        if s.quant: q = 4 * math.floor(b / 4 + 0.5) if r == 1.0 else 4 * math.floor(b * r / 4)
        else: q = b * r
        sp = L['spacing']
        if not sp: return q, q
        y = q * (1 + sp / 100)
        c = 4 * (math.ceil(y / 4 - 0.5)) if s.quant else y      # 정확히 .5 일 때 내림(한컴 확인)
        return c, q

    def width(s, ch, cs, lang): return s.width2(ch, cs, lang)[0]


def widths(model, text, cs):
    """글 전체의 (W, T): W[i] = 글자 i 의 폭, T[i] = 줄 끝에서 빼는 자간 몫(W[i]-q[i])."""
    W = []; T = []
    for c, st, l in zip(text, cs, slots(text)):
        w, q = model.width2(c, st, l); W.append(w); T.append(w - q)
    return W, T

"""줄 나눔(V3 1단계). 입력 = 글(문자열) + 글자별 폭(HWPUNIT) + 문단 줄 나눔 설정 + 줄 폭 → 출력 = 줄 시작 글자 색인 목록.
rhwp(MIT) composer/line_breaking.rs 의 동작을 읽고 우리 코드로 새로 썼다(구조·규칙 참고: 토큰화 → 줄 채우기, 금칙 문자 집합, 줄 끝 공백 매달기, 내어쓰기 줄 폭). 코드는 옮기지 않았다.

규칙(한컴 실측과 대조해 확인한 것은 devtools/linebreak_eval.py 가 숫자로 보여 준다):
- 한글 줄 나눔 기준(문단 모양 비트 7): 1 = 글자 단위(한글 음절 사이 어디서나 끊김), 0 = 어절 단위(공백에서만). 스키마 이름과 반대.
- 줄 끝 공백은 줄 폭에 세지 않고 줄에 매달린다(넘쳐도 한 개는 그 줄 마지막 글자로 흡수).
- 낱말(라틴 글자·숫자 묶음, 어절 단위의 한글 묶음)은 통째로 안 들어가면 다음 줄로. 앞에 끊을 곳이 없으면(줄에 낱말 하나뿐) 글자 단위로 억지로 끊는다.
- 행두 금칙(줄 머리에 못 오는 글자)은 앞 글자에 붙고, 행말 금칙(줄 끝에 못 오는 글자)은 뒤 글자에 붙는다.
"""

OVERFLOW_OK = 1.03
LINE_START_FORBIDDEN = set(')]},.!?;:\'"、。…·‧―ー》」』】）｝〕〉＞≫］﹞〞’”，．！？；：%‰℃°％')
LINE_END_FORBIDDEN = set('([{\'"《「『【（｛〔〈＜≪［〝‘“$₩£€¥＄￥')


def is_hangul(c):
    o = ord(c)
    return 0xAC00 <= o <= 0xD7A3 or 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F


def is_cjk_single(c):
    """한자·가나: 글자마다 낱말 하나(끊을 수 있다)."""
    o = ord(c)
    return 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0xF900 <= o <= 0xFAFF or 0x3040 <= o <= 0x30FF


def is_latin_word_char(c):
    return c.isascii() and c.isalnum() or 0xC0 <= ord(c) < 0x250


def break_positions(text, korean_unit):
    """글자 앞에서 끊을 수 있는 자리(색인 i = text[i] 앞) 집합. 공백 뒤는 항상 끊을 수 있고, 글자 단위면 한글 음절 사이, 한자·가나 사이도 끊을 수 있다."""
    ok = set()
    n = len(text)
    for i in range(1, n):
        p, c = text[i - 1], text[i]
        if p == ' ' and c != ' ': ok.add(i); continue
        if c == ' ' or c == '\n' or p == '\n': continue
        if c in LINE_START_FORBIDDEN or p in LINE_END_FORBIDDEN: continue
        if korean_unit == 1 and (is_hangul(c) or is_hangul(p)):
            ok.add(i); continue      # 글자 단위: 한글 음절 앞·뒤에서 끊을 수 있다(`회의실|(Room`, `14일|(수)` — 한컴 합성 시험으로 확인; 금칙 글자는 위에서 걸러짐)
        if is_cjk_single(c) or is_cjk_single(p):
            ok.add(i)
    return ok


def break_one(text, W, start, avail, korean_unit=1, ok=None, free=None, T=None, cond=0):
    """T: 글자마다 줄 끝에서 빼는 자간 몫(없으면 0; 한컴은 줄 마지막 글자에 자간을 안 붙인다). start 에서 시작하는 한 줄이 끝나는 자리(다음 줄 시작 색인, 공백은 건너뜀). W[i] = text[i] 의 폭(HWPUNIT, 실수). 줄 폭이 모자라면 마지막으로 끊을 수 있던 자리에서."""
    n = len(text)
    if ok is None: ok = break_positions(text, korean_unit)
    lw = 0.0; last = None; i = start; spw = 0.0; ts = 0.0; wb = 0.0      # wb: 지금 낱말(어절) 앞 내용 폭(뒤 공백 뺀 것). spw: 이 줄에 들어간 공백 폭 합(공백 압축 몫), ts: 줄 끝에 매달린 공백 폭
    f = min(cond, 100) / 100      # 공백 압축 비율. 한컴 확인: c% 가 거의 100% 까지 그대로 적용된다(공백 폭 합에 곱함)
    while i < n:
        c = text[i]
        if c == '\n': return i + 1
        if c == ' ':
            if lw + W[i] <= avail: lw += W[i]; spw += W[i]; ts += W[i]; i += 1; continue
            # 줄 폭을 넘는 공백: 줄 끝에 한 개만 매달리고 다음 줄은 그다음부터
            i += 1
            while i < n and text[i] == ' ': i += 1
            return i
        # 낱말 한 덩어리: 다음 끊을 수 있는 자리 또는 공백/줄 바꿈까지 (글자 단위 한글은 한 글자)
        if i == start or text[i - 1] == ' ': wb = lw - ts      # 글자 단위에서도 압축 조건은 낱말(어절) 시작 기준: 한컴 사다리로 확인(낱말 둘째·셋째 글자에서도 낱말 앞 내용이 압축 없이 들어가야 함)
        j = i + 1
        while j < n and j not in ok and text[j] not in ' \n': j += 1
        tw = sum(W[i:j])
        tr = T[j - 1] if T else 0      # 이 낱말이 줄 끝이 되면 마지막 글자의 자간은 안 센다
        nat = lw + tw - tr
        if nat <= avail + (0 if free is None else free) or (f and wb < avail and nat - f * spw <= avail):      # 안 들어가면 줄의 공백을 압축해 본다. 한컴: 새 낱말 앞 내용(뒤 공백 뺀 것)이 압축 없이 줄 폭 안에 있어야 한다(합성 사다리로 확인)
            lw += tw; i = j; ts = 0.0
            if i in ok or (i < n and text[i] == ' '): last = i
            continue
        if i > start and i in ok:
            return i      # 이 낱말만 다음 줄로
        if last is not None and last > start: return last
        if i == start and tw - tr <= avail * OVERFLOW_OK and not any(is_hangul(c) for c in text[i:j]): return j      # 숫자·영문 낱말 하나가 줄 폭을 3% 안쪽으로만 넘으면 폭 추정 오차로 보고 쪼개지 않는다('09:00~10:0|0' 방지). 한글은 글자 단위로 끊어도 자연스러워 해당 없음
        # 줄에 낱말 하나뿐인데 넘침: 글자 단위로 억지로 끊기(최소 한 글자)
        k = i; w = 0.0
        while k < n and (k == i or w + W[k] <= avail): w += W[k]; k += 1
        return k
    return n


def skip_spaces(text, i):
    while i < len(text) and text[i] == ' ': i += 1
    return i

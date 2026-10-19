"""2패스 vpos 되잡기(V3 2단계). 한컴이 저장한 문단 첫 줄 세로 위치(hwp2html 이 `<p data-pi data-vp data-ho>` 로 붙임)와 WeasyPrint 가 실제로 놓은 위치의 차이를 재서,
다음 문단의 위 간격에 더해 다시 배치한다. 저장 위치는 한컴 자신의 배치 기록이라 오차가 쌓이지 않게 문단마다 못 박는 효과가 난다(rhwp 가 줄 위치 오프셋 0.05pt 인 이유).
    ms = measure(doc)  ->  fx = fixes(ms)  ->  text2 = apply(text, fx)    (모두 pt 단위, WeasyPrint 내부 px 는 0.75 배로)
표 행 높이를 저장 칸 높이에 맞추는 보정(칸 안쪽 여백으로 초과분 흡수)도 시험했으나 순효과가 음수라 뺐다(평가 vp1 대 pa1: +0.005~0.018 5건, -0.1~-0.19 4건 — 한컴이 출력 환경에서 행을 저장 높이보다 크게 다시 배치하는 문서가 있다).
앵커 = 문단 첫 줄 글자 윗단 = 내용 상자 위 + data-ho(줄 상자 안 위 반 줄 간격). 한 쪽의 첫 문단은 본문 위에서의 절대 위치로, 나머지는 앞 문단과의 간격으로 맞춘다."""
import os, re

LIMIT = float(os.environ.get('VPOS_LIMIT', 30))        # pt. 이보다 크게 고쳐야 하면 쪽·개체 구성이 다른 것이니 건드리지 않는다
FIRST_MAX = float(os.environ.get('VPOS_FIRST_MAX', 150))      # pt. 쪽 첫 문단의 저장 위치가 이보다 크면 한컴은 그 문단이 쪽 중간에 있다(우리 쪽 나눔이 다름)
TOL = 0.15      # pt. 이 안이면 안 고친다
FIRST = os.environ.get('VPOS_FIRST', 'on')      # off 면 쪽 첫 문단의 절대 위치 보정을 안 한다


def measure(doc):
    """[{pi, page, rel, vp}]: 문단 첫 조각만(쪽을 넘어 이어진 뒷조각은 뺀다). rel = 쪽 본문 위에서 첫 줄 글자 윗단까지(pt).
    (시도: 앞이 표·그림이면 그 아랫선까지만 당기게 제한 — cell-page 의 글/표 겹침은 막지만 표가 한컴보다 큰 문서가 표 안쪽까지 당겨야 쪽에 맞는 경우(taxi_press 0.624→0.168, 1쪽→2쪽)를 잃어 되돌렸다. 뿌리는 표 높이 오차.)"""
    from weasyprint.formatting_structure import boxes
    seen, out = set(), []
    def walk(b):
        yield b
        for c in getattr(b, 'children', None) or ():
            yield from walk(c)
    for pn, page in enumerate(doc.pages):
        pb = page._page_box; top = pb.content_box_y()
        for b in walk(pb):
            e = getattr(b, 'element', None)
            if e is None or not isinstance(b, boxes.BlockBox) or getattr(b, 'element_tag', None) != 'p': continue
            pi = e.get('data-pi')
            if pi is None or pi in seen: continue
            seen.add(pi)
            out.append(dict(pi=int(pi), page=pn, rel=(b.content_box_y() - top + float(e.get('data-ho'))) * 0.75, vp=float(e.get('data-vp')), ho=float(e.get('data-ho')) * 0.75))
    last = {}      # 문단이 쪽을 넘어 이어지면 마지막 조각이 놓인 쪽
    for pn, page in enumerate(doc.pages):
        for b in walk(page._page_box):
            e = getattr(b, 'element', None)
            if e is not None and isinstance(b, boxes.BlockBox) and getattr(b, 'element_tag', None) == 'p' and e.get('data-pi') is not None: last[int(e.get('data-pi'))] = pn
    for m in out: m['end'] = last.get(m['pi'], m['page'])
    return out


def usable(ms):
    """저장 위치를 믿을 수 있는 문서인가(fixes 와 같은 검사: 위치 0 이 너무 많거나 저장 간격이 없다시피 한 쌍이 많으면 낡은 파일)."""
    zeros = sum(1 for m in ms if m['vp'] == 0); pages = len({m['page'] for m in ms})
    if len(ms) >= 4 and zeros > max(2 * pages, 0.3 * len(ms)): return False
    last, pairs, stale = {}, 0, 0
    for m in ms:
        prev = last.get(m['page']); last[m['page']] = m
        if prev is None: continue
        g, a = m['vp'] - prev['vp'], m['rel'] - prev['rel']
        if g < 0 or a < 0 or a <= 6: continue
        pairs += 1
        if g < 0.2 * a: stale += 1
    return not (pairs >= 4 and stale >= 0.25 * pairs)


def fixes(ms):
    """{pi: (δ pt, 쪽 첫 문단이냐)}: δ>0 이면 우리 문단이 한컴보다 위에 있으니 위 간격을 늘린다.
    저장 위치가 쓸 수 없는 문서(줄 위치가 전부 0 같은 낡은 HWPX: 저장 간격이 0 이라 '문단 높이만큼 위로 당기기'가 돼 모든 문단이 겹친다 — outline_navigation_panel_demo 0.81→0.05)는
    저장 간격이 우리 간격의 20% 미만인 쌍이 25% 를 넘으면 문서 전체를 건드리지 않는다."""
    zeros = sum(1 for m in ms if m['vp'] == 0); pages = len({m['page'] for m in ms})
    if len(ms) >= 4 and zeros > max(2 * pages, 0.3 * len(ms)): return {}      # 정상 문서에서 저장 위치 0 은 쪽 시작에서만 나온다. 그보다 훨씬 많으면 저장 위치를 안 채운 낡은 파일(추진일정.hwpx 96%·cell-page 90%·underline_run 49%)
    fx, last, pairs, stale = {}, {}, 0, 0
    for m in ms:
        prev = last.get(m['page']); last[m['page']] = m
        if prev is None:
            if FIRST == 'off': continue      # 쪽 첫 문단을 본문 위에 절대 위치로 못 박는 단계를 끈다(실험)
            d = m['vp'] - m['rel']; first = True
            if m['vp'] > FIRST_MAX: continue
        else:
            g, a = m['vp'] - prev['vp'], m['rel'] - prev['rel']; first = False
            if g < 0 or a < 0: continue      # 한컴 쪽·단이 바뀌었거나 우리 단이 바뀜: 이 쌍은 못 잰다
            if a > 6:
                pairs += 1
                if g < 0.2 * a: stale += 1; continue      # 저장 간격이 없다시피 함 = 저장 위치를 못 믿는다
            d = g - a
        if abs(d) > LIMIT or abs(d) < TOL: continue
        fx[m['pi']] = (round(d, 2), first)
    return {} if pairs >= 4 and stale >= 0.25 * pairs else fx


BRK = os.environ.get('VPOS_BRK', 'on')      # off 면 쪽 나눔 맞추기를 안 한다
BRK_DROP = 30.0      # pt. 저장 위치가 이만큼 이상 거꾸로 가야 한컴이 쪽(단)을 바꾼 것으로 본다


def breaks(ms, ok=True):
    """{pi: (δ, True)}: 한컴은 이 문단 앞에서 쪽을 바꿨는데(저장 위치가 거꾸로 감) 우리는 앞 문단과 같은 쪽에 두고 있다 = 우리가 한 쪽에 더 담는 경우.
    그때만 이 문단 앞에서 쪽을 나눈다. 한컴의 그 쪽 내용(앞 쪽 나눔 뒤 ~ 이 문단 앞)이 우리 쪽 한 장에 다 들어 있을 때만 — 우리가 이미 덜 담고 있으면(그 내용이 우리 두 쪽에 걸침)
    나눔을 더하면 거의 빈 쪽이 생기니 건드리지 않는다(STORED_LAYOUT=all 이 해로웠던 이유). δ = 쪽 맨 위에서의 저장 위치 - 줄 상자 안 위 반 줄 간격(쪽 첫 문단 맞춤과 같은 규칙)."""
    if BRK == 'off' or not ok: return {}
    out, start = {}, 0
    for i in range(1, len(ms)):
        a, b = ms[i - 1], ms[i]
        if a['vp'] - b['vp'] > BRK_DROP and b['vp'] <= FIRST_MAX:      # 한컴이 여기서 쪽을 바꿨다
            if b['page'] == a['end'] and ms[start]['page'] == a['end']:      # 우리는 같은 쪽 + 그 쪽 내용이 우리 한 쪽 안
                d = round(b['vp'] - b['ho'], 2)
                out[b['pi']] = (d if abs(d) <= LIMIT and abs(d) >= TOL else 0.0, True)
            start = i
    return out


def stored_pages(ms):
    """저장된 위치가 거꾸로 간 횟수 + 1 = 한컴이 낸 쪽 수의 어림(태그가 붙은 문단만 보니 표·그림만 있는 쪽은 못 센다 → 적게 나올 수 있다)."""
    return 1 + sum(1 for i in range(1, len(ms)) if ms[i - 1]['vp'] - ms[i]['vp'] > BRK_DROP and ms[i]['vp'] <= FIRST_MAX) if len(ms) >= 10 else 0


def prefer_first(n_stored, pages1, pages2):
    """2패스가 1패스보다 쪽을 늘렸을 때(위 간격을 늘려 쪽 끝에서 밀림) 저장 쪽 수 어림에 1패스가 더 가까우면 1패스 결과를 쓴다."""
    return bool(n_stored) and pages2 > pages1 and abs(pages1 - n_stored) <= abs(pages2 - n_stored)


def apply(text, fx, br=None):
    """`<p … data-pi="N" … style="…">` 의 위 간격을 δ 만큼 고친다(쪽 첫 문단이 양수면 padding-top: 쪽 맨 위에서 margin 은 버려질 수 있다). 값 단위는 px(HWP)·pt(HWPX) 둘 다."""
    br = br or {}
    def one(m):
        pi = int(m.group(2)); tag = m.group(0)
        if pi in br: tag = re.sub(r'(style="[^"]*)"', r'\1;break-before:page"', tag, count=1)      # 쪽 나눔 먼저(여기서 한컴이 쪽을 바꿨다), 이어서 쪽 첫 문단 위치 보정
        ent = fx.get(pi) or (br[pi] if pi in br and br[pi][0] else None)
        if ent is None: return tag
        d, first = ent
        prop = 'padding-top' if first and d > 0 else 'margin-top'
        mm = re.search(r'(?<![-\w])%s:(-?[\d.]+)(px|pt)' % prop, tag)
        if mm: return tag[:mm.start(1)] + '%.2f' % (float(mm.group(1)) + d * (4 / 3 if mm.group(2) == 'px' else 1)) + tag[mm.end(1):]
        return tag[:-2] + ';%s:%.2fpt">' % (prop, d) if tag.endswith('">') else tag
    return re.sub(r'<p( [^>]*?data-pi="(\d+)"[^>]*?)>', one, text)


VZ_MAX = float(os.environ.get('VPOS_VZ_MAX', 0.30))      # 줄 위치가 0 인 줄이 이 비율을 넘는 문서는 저장 위치를 안 채운 낡은 파일(정상 문서에서 0 은 쪽 시작 줄뿐: 쪽 수/줄 수)


def trusted(text):
    """문서가 알려 준 줄 위치 0 비율(<meta name="hwp-vz">)이 VZ_MAX 이하일 때 저장 위치를 믿는다. 표시가 없으면(본문 줄 10개 미만의 작은 문서) 믿는다 —
    그런 문서의 낡은 값은 fixes() 의 쌍 검사(저장 간격이 우리 간격의 20% 미만)가 막는다."""
    m = re.search(r'<meta name="hwp-vz" content="([\d.]+)"', text)
    return float(m.group(1)) <= VZ_MAX if m else True


SLACK = os.environ.get('SLACK_FIX', 'off')      # 'on' 이면 쪽 끝 허용을 켠다(평가 중 시험: 기본 꺼짐)
SLACK_CAP = float(os.environ.get('SLACK_CAP', 6))      # pt. 쪽 아래 허용 상한: 한컴이 쪽 끝 줄을 놓는 기준(글 아래끝)과 우리 줄 상자(글 + 아래 줄 간격) 차이·쪽 위 1~2pt 오차를 흡수한다


def slacks(doc, ms):
    """{쪽 번호(1부터): 허용 pt}: 한컴 저장 위치로 '한컴은 다음 문단 b 의 첫 줄을 이 쪽에 뒀다'가 증명되는데 우리는 쪽을 바꾼 자리(우리가 덜 담음)에서만 그 쪽 아래 여백을 줄인다.
    증거 = b 가 앞 문단 a 와 같은 쪽 좌표(저장 위치가 아래로 이어짐)이고 b 첫 줄 글 아래끝이 한컴 본문 안. 그 쪽 위에서 b 첫 줄이 모자란 만큼의 하한이 SLACK_CAP 이하일 때만(큰 모자람은 쪽 끝 판정 말고 다른 원인: 쪽 안 높이 차·표).
    전 쪽에 같은 값을 주는 PAGE_SLACK 은 이미 맞던 문서(표 행이 쪽 끝에 놓인 문서)를 후퇴시켰다 — 증거가 있는 쪽에만 준다."""
    from weasyprint.formatting_structure import boxes
    def walk(b, pi=None):
        e = getattr(b, 'element', None)
        if e is not None and getattr(b, 'element_tag', None) == 'p' and e.get('data-pi') is not None: pi = int(e.get('data-pi'))
        yield b, pi
        for c in getattr(b, 'children', None) or ():
            yield from walk(c, pi)
    geo = []
    for page in doc.pages:
        pb = page._page_box; top = pb.content_box_y(); mb = 0.0; first = None
        for c in pb.children:
            if isinstance(c, boxes.MarginBox): continue
            for b, pi in walk(c):
                if isinstance(b, (boxes.TableBox, boxes.ReplacedBox, boxes.LineBox)) and isinstance(b.height, (int, float)): mb = max(mb, b.position_y + b.height)
                if isinstance(b, boxes.LineBox) and (first is None or b.position_y < first[0]): first = (b.position_y, b.position_y + b.height - top, pi)
        geo.append(dict(top=top, bottom=top + pb.height, maxb=mb, first=first, mgb=pb.margin_bottom))
    out = {}
    for a, b in zip(ms, ms[1:]):
        p = a['end']
        if b['page'] != p + 1 or p + 1 >= len(geo) or b['vp'] <= a['vp']: continue      # 문단 사이 쪽 경계만(문단 중간 경계는 저장 위치가 첫 줄 것이라 증거가 못 된다)
        g, nx = geo[p], geo[p + 1]
        if nx['first'] is None or nx['first'][2] != b['pi']: continue      # 다음 쪽 첫 줄이 b 의 것일 때만
        h1 = nx['first'][1] * 0.75; hbody = (g['bottom'] - g['top']) * 0.75
        need_lo = (g['maxb'] + nx['first'][1] - g['bottom']) * 0.75
        if b['vp'] + h1 - 2 * b['ho'] <= hbody + 1.0 and need_lo <= SLACK_CAP: out[p + 1] = (round(SLACK_CAP, 2), g['mgb'] * 0.75)
    return out


def slack_css(sl):
    """쪽마다 아래 여백을 허용만큼 줄이는 CSS(@page:nth). 이름 있는 쪽 규칙(구역 둘째부터)보다 이기도록 !important."""
    return ''.join('@page:nth(%d){margin-bottom:%.2fpt!important}\n' % (n, max(0.0, mg - s)) for n, (s, mg) in sorted(sl.items()))

OVERLAP_MIN = 1.5      # pt. 위로 당긴 문단 글이 앞 상자(표·그림·문단)의 아랫선을 이만큼 넘게 파고들면 겹침으로 본다


def overlaps(doc, fx):
    """{pi: 겹친 pt}: 위로 당긴(δ<0) 문단 중, 보이는 첫 줄 윗단(내용 상자 위 + 줄 상자 안 위 반 줄 간격)이 바로 앞 상자의 아랫선보다 OVERLAP_MIN 넘게 위인 것.
    한컴이 저장한 위치로 당기는데 우리 표·그림이 한컴보다 커서 당겨진 글이 그 안으로 파고드는 경우(pr-1674 쪽 14 '참고' 표 아래 문단: 표 9pt 큼 + 앞 배치 차로 -23.7pt 당김 → 글이 표 아랫선에 15pt 겹침)."""
    from weasyprint.formatting_structure import boxes
    neg = {pi for pi, v in fx.items() if v[0] < 0}
    if not neg or os.environ.get('OVERLAP_FIX') != 'on': return {}      # 기본 꺼짐: 시험(t123)에서 img-start-001 −0.30·hongbo −0.095·공문서양식 −0.063 등 후퇴(앞 상자 아랫선보다 위로 당기는 것이 한컴 저장 위치대로인 문서가 많다)
    out = {}
    def walk(b):
        ch = getattr(b, 'children', None) or ()
        prev = None
        for c in ch:
            e = getattr(c, 'element', None)
            if prev is not None and isinstance(c, boxes.BlockBox) and e is not None and getattr(c, 'element_tag', None) == 'p' and e.get('data-pi') is not None:
                pi = int(e.get('data-pi'))
                if pi in neg and pi not in out and getattr(prev, 'position_y', None) is not None:
                    ov = (prev.border_box_y() + prev.border_height() - (c.content_box_y() + float(e.get('data-ho')))) * 0.75
                    if ov > OVERLAP_MIN: out[pi] = round(ov, 2)
            if isinstance(c, boxes.Box) and not isinstance(c, (boxes.TextBox, boxes.LineBox)): walk(c)
            if isinstance(c, (boxes.BlockBox, boxes.TableBox)) and not c.is_floated() and not c.is_absolutely_positioned(): prev = c      # 흐름 안 상자만(떠 있는 그림·고정 상자는 글 높이와 무관)
    for page in doc.pages: walk(page._page_box)
    return out

"""한글 차트 -> 인라인 SVG. 한글 차트는 OOXML 차트 XML(c:chartSpace)로 저장된다: HWPX 는 Chart/chartN.xml, HWP 는 BinData/BINxxxx.OLE(안에 든 OLE 복합 파일)의 /OOXMLChartContents 스트림.
시리즈 값·범주가 캐시(strCache·numCache)로 들어 있어 엑셀 원본 없이 그릴 수 있다. 지원: 원형(3D·도넛·원형 대 원형)·세로/가로 막대(묶은·누적·100% 누적)·꺾은선·영역·분산형·주식형(고가-저가-종가·시가-고가-저가-종가).
그 밖의 종류(방사형·거품 등)와 읽을 수 없는 XML 은 None — 호출한 쪽이 예전처럼 아무것도 안 그린다. 한컴 PDF 와 나란히 본 모양(제목·범례 오른쪽·Office 2013 색)을 따르되 3D 는 납작한 근사다.
render(xml, w_pt, h_pt) -> '<svg …>' 또는 None.  (2026-10-13 구현, 시험·평가는 다음 세션: docs/현재상태.md '차트' 항목 참조)"""
import html, math, re
import xml.etree.ElementTree as ET

C = '{http://schemas.openxmlformats.org/drawingml/2006/chart}'
A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
PALETTE = ['4472C4', 'ED7D31', 'A5A5A5', 'FFC000', '5B9BD5', '70AD47', '264478', '9E480E', '636363', '997300']      # Office 2013 계열 색(한컴 차트 기본과 같게 보임)
SCHEME = {'accent1': '4472C4', 'accent2': 'ED7D31', 'accent3': 'A5A5A5', 'accent4': 'FFC000', 'accent5': '5B9BD5', 'accent6': '70AD47', 'tx1': '000000', 'dk1': '000000', 'bg1': 'FFFFFF', 'lt1': 'FFFFFF', 'tx2': '44546A', 'bg2': 'E7E6E6'}
FONT = "'함초롬돋움','Malgun Gothic','Nanum Gothic',sans-serif"
GRID, AXIS = '#d9d9d9', '#868686'


def esc(s): return html.escape(str(s), quote=True)


def tw(text, size):      # 글 폭 어림(한글·전각 1.0, 그 밖 0.55)
    return sum(size * (1.0 if ord(c) > 0x2E80 else 0.55) for c in str(text))


def num(v):
    if v is None: return ''
    return ('%d' % v) if abs(v - round(v)) < 1e-9 and abs(v) < 1e15 else ('%.10g' % v)


def color(el):
    """el 아래 첫 단색 채움/선 색 -> '#RRGGBB' 또는 None."""
    if el is None: return None
    sf = el.find('.//' + A + 'solidFill')
    if sf is None: return None
    c = sf.find(A + 'srgbClr')
    if c is not None: return '#' + c.get('val')
    c = sf.find(A + 'schemeClr')
    return ('#' + SCHEME[c.get('val')]) if c is not None and c.get('val') in SCHEME else None


def nice_axis(lo, hi, n=5):
    """눈금: (최소, 최대, 간격). 0 을 포함하게 잡는다(막대·선 기본)."""
    lo, hi = min(lo, 0), max(hi, 0)
    if hi == lo: hi = lo + 1
    raw = (hi - lo) / n; mag = 10 ** math.floor(math.log10(raw)); f = raw / mag
    step = mag * (1 if f <= 1 else 2 if f <= 2 else 5 if f <= 5 else 10)
    return math.floor(lo / step) * step, math.ceil(hi / step) * step, step


def pts(el, cast=str):
    """c:cat·c:val 등의 캐시 점들 -> 번호순 리스트(없는 점은 None)."""
    if el is None: return []
    cnt = el.find('.//' + C + 'ptCount'); n = int(cnt.get('val')) if cnt is not None else 0
    out = [None] * n
    for p in el.iter(C + 'pt'):
        i = int(p.get('idx')); v = p.findtext(C + 'v')
        while i >= len(out): out.append(None)
        try: out[i] = cast(v)
        except (TypeError, ValueError): out[i] = None
    return out


def parse_ser(s, k):
    sp = s.find(C + 'spPr')
    d = dict(name=s.findtext('.//' + C + 'tx//' + C + 'v') or '', cats=pts(s.find(C + 'cat')), vals=pts(s.find(C + 'val') if s.find(C + 'val') is not None else s.find(C + 'yVal'), float),
             xs=pts(s.find(C + 'xVal'), float), fill=color(sp) or '#' + PALETTE[k % len(PALETTE)], pt={}, nofill=sp is not None and sp.find(A + 'noFill') is not None)
    ln = sp.find(A + 'ln') if sp is not None else None
    d['line'] = color(ln) if ln is not None else None
    d['noline'] = ln is not None and ln.find(A + 'noFill') is not None
    mk = s.find(C + 'marker'); d['marker'] = None if mk is None else (mk.findtext(C + 'symbol') or 'auto')
    for dp in s.findall(C + 'dPt'):
        c = color(dp.find(C + 'spPr'))
        if c: d['pt'][int(dp.find(C + 'idx').get('val'))] = c
    if not d['cats']: d['cats'] = [str(i + 1) for i in range(len(d['vals']))]
    return d


def wedge(cx, cy, r, ry, a0, a1, inner=0.0):
    """각도 a0→a1(라디안, 12시 방향이 0, 시계 방향) 부채꼴 경로. ry 는 3D 의 납작한 세로 반지름."""
    p = lambda a, rr, rry: (cx + rr * math.sin(a), cy - rry * math.cos(a))
    x0, y0 = p(a0, r, ry); x1, y1 = p(a1, r, ry); big = 1 if a1 - a0 > math.pi else 0
    if inner:
        xi1, yi1 = p(a1, r * inner, ry * inner); xi0, yi0 = p(a0, r * inner, ry * inner)
        return 'M%.2f %.2f A%.2f %.2f 0 %d 1 %.2f %.2f L%.2f %.2f A%.2f %.2f 0 %d 0 %.2f %.2f Z' % (x0, y0, r, ry, big, x1, y1, xi1, yi1, r * inner, ry * inner, big, xi0, yi0)
    if a1 - a0 >= 2 * math.pi - 1e-6:
        return 'M%.2f %.2f A%.2f %.2f 0 1 1 %.2f %.2f A%.2f %.2f 0 1 1 %.2f %.2f Z' % (cx, cy - ry, r, ry, cx, cy + ry, r, ry, cx, cy - ry)
    return 'M%.2f %.2f L%.2f %.2f A%.2f %.2f 0 %d 1 %.2f %.2f Z' % (cx, cy, x0, y0, r, ry, big, x1, y1)


def shade(hexc, k):
    h = hexc.lstrip('#'); r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return '#%02x%02x%02x' % tuple(max(0, min(255, int(v * k))) for v in (r, g, b))


def render(xml, w, h):
    try: root = ET.fromstring(xml if isinstance(xml, (bytes, str)) else bytes(xml))
    except ET.ParseError: return None
    chart = root.find(C + 'chart'); plot = chart.find(C + 'plotArea') if chart is not None else None
    if plot is None or w <= 0 or h <= 0: return None
    groups = [g for g in plot if g.tag.startswith(C) and g.tag.endswith('Chart')]
    kinds = [g.tag[len(C):-5] for g in groups]      # 'pie3D' 만 3D 로 남기고, 막대·선·영역의 3D 는 2D 로 그린다
    kinds = [k[:-2] if k.endswith('3D') and k != 'pie3D' else k for k in kinds]
    if not groups or any(k not in ('pie', 'pie3D', 'ofPie', 'doughnut', 'bar', 'line', 'area', 'scatter', 'stock') for k in kinds): return None
    sers = []
    for g in groups:
        for k, s in enumerate(g.findall(C + 'ser')): sers.append(parse_ser(s, len(sers)))
    if not sers: return None
    sz_el = root.find('.//' + A + 'defRPr'); base = (int(sz_el.get('sz')) / 100) if sz_el is not None and sz_el.get('sz') else 10.0
    out = []; add = out.append
    cs = root.find(C + 'spPr')
    border = '#d9d9d9' if cs is None or cs.find(A + 'ln') is None or cs.find(A + 'ln').find(A + 'noFill') is None else 'none'
    add('<rect x="0.5" y="0.5" width="%.2f" height="%.2f" fill="#fff" stroke="%s" stroke-width="0.75"/>' % (w - 1, h - 1, border))
    T = lambda x, y, s, size=base, anchor='start', extra='': add('<text x="%.2f" y="%.2f" font-size="%.2f" text-anchor="%s" fill="#404040"%s>%s</text>' % (x, y, size, anchor, extra, esc(s)))
    pad = 6.0; top, bot, left, right = pad, h - pad, pad, w - pad
    t = chart.find(C + 'title')
    if t is not None and (chart.find(C + 'autoTitleDeleted') is None or chart.find(C + 'autoTitleDeleted').get('val') != '1'):
        text = ''.join(x.text or '' for x in t.iter(A + 't')) or (sers[0]['name'] if len(sers) == 1 else '차트 제목')
        ts = base * 1.4; T(w / 2, top + ts * 0.95, text, ts, 'middle'); top += ts * 1.6
    pie_like = kinds[0] in ('pie', 'pie3D', 'ofPie', 'doughnut')
    lg = chart.find(C + 'legend')
    if lg is not None:      # 범례: 오른쪽(기본)·왼쪽·위·아래
        pos = (lg.find(C + 'legendPos').get('val') if lg.find(C + 'legendPos') is not None else 'r')
        ents = [(c, sers[0]['pt'].get(i) or '#' + PALETTE[i % len(PALETTE)]) for i, c in enumerate(sers[0]['cats'])] if pie_like else [(s['name'] or '계열%d' % (i + 1), s['line'] or s['fill']) for i, s in enumerate(sers)]
        lh = base * 1.5
        if pos in ('r', 'l', 'tr'):
            lw = max(tw(n, base) for n, _ in ents) + base * 2.2; x0 = (right - lw) if pos != 'l' else left; y0 = (top + bot) / 2 - lh * len(ents) / 2
            for i, (n, c) in enumerate(ents):
                add('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s"/>' % (x0, y0 + i * lh + lh * 0.2, base * 0.6, base * 0.6, c)); T(x0 + base * 1.0, y0 + i * lh + lh * 0.75, n)
            if pos == 'l': left += lw
            else: right -= lw + base * 0.5
        else:
            tot = sum(tw(n, base) + base * 2.2 for n, _ in ents); x0 = (w - tot) / 2; y0 = (bot - lh) if pos == 'b' else top
            for n, c in ents:
                add('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s"/>' % (x0, y0 + lh * 0.2, base * 0.6, base * 0.6, c)); T(x0 + base * 1.0, y0 + lh * 0.75, n); x0 += tw(n, base) + base * 2.2
            if pos == 'b': bot -= lh + base * 0.3
            else: top += lh + base * 0.3
    if pie_like: _pie(groups[0], kinds[0], sers[0], (left, top, right, bot), add, base)
    elif kinds[0] == 'stock': _stock(groups, sers, (left, top, right, bot), add, T, base)
    else: _cart(groups, kinds, sers, (left, top, right, bot), add, T, base)
    return '<svg xmlns="http://www.w3.org/2000/svg" width="%gpt" height="%gpt" viewBox="0 0 %.2f %.2f" style="display:block;overflow:hidden;font-family:%s">%s</svg>' % (w, h, w, h, FONT.replace('"', "'"), ''.join(out))


def _pie(g, kind, s, box, add, base):
    l, t, r, b = box; vals = [v or 0.0 for v in s['vals']]; n = len(vals)
    first = g.find(C + 'firstSliceAng'); ang0 = math.radians(int(first.get('val')) if first is not None else 0)
    three = kind == 'pie3D'; ry_k = 0.6 if three else 1.0
    cols = [s['pt'].get(i) or '#' + PALETTE[i % len(PALETTE)] for i in range(n)]
    if kind == 'ofPie':       # 원형 대 원형: 뒤쪽 k 점을 '기타' 한 조각으로 묶어 큰 원에, 그 점들은 작은 원(오른쪽)에. k 는 점이 5개 이하면 2, 그 이상 3(한컴 기본을 모른다 — 근사)
        k = 2 if n <= 5 else 3; k = min(k, n - 1)
        sp = g.find(C + 'secondPieSize'); sc = (int(sp.get('val')) if sp is not None else 75) / 100
        main = vals[:n - k] + [sum(vals[n - k:])]; mcols = cols[:n - k] + ['#' + PALETTE[(n + 1) % len(PALETTE)]]      # '기타' 조각 색: 한컴은 점 색 다음 색(초록 계열)
        R = min((r - l) / (2 + 0.35 + 2 * sc), (b - t) / 2) * 0.95; cx = l + R; cy = (t + b) / 2; tot = sum(main) or 1; other = 2 * math.pi * main[-1] / tot
        ta, ba = math.pi / 2 - other / 2, math.pi / 2 + other / 2; a = ba        # '기타' 조각(마지막)이 3시 방향 가운데: 첫 조각은 그 아래 끝에서 시계 방향으로
        for v, c in zip(main, mcols):
            da = 2 * math.pi * v / tot; add('<path d="%s" fill="%s" stroke="#fff" stroke-width="0.5"/>' % (wedge(cx, cy, R, R, a, a + da), c)); a += da
        R2 = R * sc; cx2 = cx + R + R2 + R * 0.35; sub = vals[n - k:]; tot2 = sum(sub) or 1; a2 = 0.0
        # 연결선: 큰 원의 '기타' 조각 위·아래 끝에서 작은 원의 위·아래 끝으로
        add('<path d="M%.2f %.2f L%.2f %.2f M%.2f %.2f L%.2f %.2f" stroke="#868686" stroke-width="0.6" fill="none"/>' % (cx + R * math.sin(ta), cy - R * math.cos(ta), cx2, cy - R2, cx + R * math.sin(ba), cy - R * math.cos(ba), cx2, cy + R2))
        for v, c in zip(sub, cols[n - k:]):
            da = 2 * math.pi * v / tot2; add('<path d="%s" fill="%s" stroke="#fff" stroke-width="0.5"/>' % (wedge(cx2, cy, R2, R2, a2, a2 + da), c)); a2 += da
        return
    R = min((r - l) / 2, (b - t) / 2 / ry_k) * (0.9 if three else 0.95); cx = (l + r) / 2; cy = (t + b) / 2 - (R * 0.06 if three else 0); tot = sum(vals) or 1; depth = R * 0.14 if three else 0
    hole = (int(g.find(C + 'holeSize').get('val')) / 100) if kind == 'doughnut' and g.find(C + 'holeSize') is not None else (0.5 if kind == 'doughnut' else 0)
    for layer in ((1, 0) if three else (0,)):      # 3D: 먼저 어두운 아래 면(아래로 depth 만큼), 그 위에 윗면
        a = ang0
        for v, c in zip(vals, cols):
            da = 2 * math.pi * v / tot
            if da > 1e-9: add('<path d="%s" fill="%s" stroke="#fff" stroke-width="0.5"/>' % (wedge(cx, cy + (depth if layer else 0), R, R * ry_k, a, a + da, hole), shade(c, 0.7) if layer else c))
            a += da


def _cart(groups, kinds, sers, box, add, t, base):
    l, tp, r, b = box; first = kinds[0]; bd = groups[0].find(C + 'barDir'); horiz = first == 'bar' and bd is not None and bd.get('val') == 'bar'
    gp = groups[0].find(C + 'grouping'); grouping = gp.get('val') if gp is not None else 'clustered'
    stacked = grouping in ('stacked', 'percentStacked') and first in ('bar', 'area')
    allv = [v for s in sers for v in s['vals'] if v is not None]
    n = max(len(s['cats']) for s in sers) if first != 'scatter' else 0
    if stacked:
        pos_ = [sum(max(s['vals'][i] or 0, 0) for s in sers if i < len(s['vals'])) for i in range(n)]; neg_ = [sum(min(s['vals'][i] or 0, 0) for s in sers if i < len(s['vals'])) for i in range(n)]
        lo, hi, step = (0, 1, 0.2) if grouping == 'percentStacked' else nice_axis(min(neg_ + [0]), max(pos_ + [0]))
    else: lo, hi, step = nice_axis(min(allv + [0]), max(allv + [0])) if allv else (0, 1, 0.2)
    ticks = []; v = lo
    while v <= hi + step * 1e-6: ticks.append(v); v += step
    fmtv = (lambda v: num(round(v * 100, 6)) + '%') if grouping == 'percentStacked' else (lambda v: num(round(v, 10)))
    ch = base * 1.5
    if horiz: l += max(tw(c, base) for c in sers[0]['cats']) + 6
    else: l += max(tw(fmtv(v), base) for v in ticks) + 6
    b -= ch
    va = lambda v: (l + (r - l) * (v - lo) / (hi - lo)) if horiz else (b + (tp - b) * (v - lo) / (hi - lo))      # 값 -> 화면 좌표(가로 막대는 x, 나머지는 y)
    for v in ticks:      # 눈금선·값 눈금 글
        q = va(v)
        if horiz: add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="0.5"/>' % (q, tp, q, b, GRID)); t(q, b + base * 1.2, fmtv(v), base, 'middle')
        else: add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="0.5"/>' % (l, q, r, q, GRID)); t(l - 4, q + base * 0.35, fmtv(v), base, 'end')
    if first == 'scatter':
        allx = [v for s in sers for v in s['xs'] if v is not None] or list(range(len(allv)))
        xl, xh, xs = nice_axis(min(allx + [0]), max(allx + [0])); px = lambda v: l + (r - l) * (v - xl) / (xh - xl); v = xl
        while v <= xh + xs * 1e-6: t(px(v), b + base * 1.2, num(round(v, 10)), base, 'middle'); v += xs
        ss = (groups[0].find(C + 'scatterStyle').get('val') if groups[0].find(C + 'scatterStyle') is not None else '')
        for s in sers:
            xy = [(px(x), va(y)) for x, y in zip(s['xs'] or range(len(s['vals'])), s['vals']) if y is not None and x is not None]
            if len(xy) > 1 and not s['noline'] and ss.startswith('line'): add('<polyline points="%s" fill="none" stroke="%s" stroke-width="1.5"/>' % (' '.join('%.2f,%.2f' % q for q in xy), s['line'] or s['fill']))
            for x, y in xy: add('<circle cx="%.2f" cy="%.2f" r="2.5" fill="%s"/>' % (x, y, s['fill']))
        add('<path d="M%.2f %.2f V%.2f H%.2f" fill="none" stroke="%s" stroke-width="0.75"/>' % (l, tp, b, r, AXIS)); return
    band = ((b - tp) if horiz else (r - l)) / n
    pos = lambda i: (tp if horiz else l) + band * (i + 0.5)          # 범주 i 의 가운데(가로 막대는 y, 나머지는 x)
    cats = max(sers, key=lambda s: len(s['cats']))['cats']
    for i, c in enumerate(cats):
        if horiz: t(l - 4, pos(i) + base * 0.35, c, base, 'end')
        else: t(pos(i), b + base * 1.2, c, base, 'middle')
    z = va(0); k0 = 0
    for g, kk in zip(groups, kinds):
        gs = sers[k0:k0 + len(g.findall(C + 'ser'))]; k0 += len(gs)
        if kk == 'bar':
            gw = g.find(C + 'gapWidth'); gap = (int(gw.get('val')) if gw is not None else 150) / 100
            m = 1 if stacked else len(gs); bw = band / (m + gap)
            for i in range(n):
                acc_p = acc_n = 0.0; tot = sum(abs(s['vals'][i] or 0) for s in gs if i < len(s['vals'])) or 1
                for j, s in enumerate(gs):
                    v = s['vals'][i] if i < len(s['vals']) else None
                    if v is None: continue
                    if grouping == 'percentStacked': v = v / tot
                    if stacked:
                        if v >= 0: a0 = acc_p; acc_p += v; a1 = acc_p
                        else: a0 = acc_n; acc_n += v; a1 = acc_n
                        off = bw * gap / 2
                    else: a0, a1 = 0, v; off = bw * gap / 2 + j * bw
                    c = s['pt'].get(i) or s['fill']; q0, q1 = sorted((va(a0), va(a1)))
                    if horiz: add('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s"/>' % (q0, pos(i) - band / 2 + off, q1 - q0, bw, c))
                    else: add('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s"/>' % (pos(i) - band / 2 + off, q0, bw, q1 - q0, c))
        else:      # 꺾은선·영역
            for s in gs:
                p = [(pos(i), va(v)) for i, v in enumerate(s['vals']) if v is not None]
                if not p: continue
                if kk == 'area': add('<polygon points="%s" fill="%s" fill-opacity="0.85"/>' % (' '.join('%.2f,%.2f' % q for q in [(p[0][0], z)] + p + [(p[-1][0], z)]), s['fill']))
                elif not s['noline']: add('<polyline points="%s" fill="none" stroke="%s" stroke-width="2"/>' % (' '.join('%.2f,%.2f' % q for q in p), s['line'] or s['fill']))
                if kk == 'line' and s['marker'] != 'none':
                    for x, y in p: add('<circle cx="%.2f" cy="%.2f" r="2.6" fill="%s"/>' % (x, y, s['line'] or s['fill']))
    add('<path d="M%.2f %.2f V%.2f H%.2f" fill="none" stroke="%s" stroke-width="0.75"/>' % (l, tp, b, r, AXIS))


def _stock(groups, sers, box, add, t, base):
    """주식형: 범주마다 가장 높은 값~가장 낮은 값을 세로선(hiLowLines)으로, 시가-고가-저가-종가면 시가~종가를 위아래 막대(upDownBars)로, 고가-저가-종가면 종가에 오른쪽 짧은 눈금."""
    l, tp, r, b = box; n = max(len(s['cats']) for s in sers); allv = [v for s in sers for v in s['vals'] if v is not None] or [0, 1]
    lo, hi, step = nice_axis(min(allv + [0]), max(allv)); ticks = []; v = lo
    while v <= hi + step * 1e-6: ticks.append(v); v += step
    lw = max(tw(num(round(v, 10)), base) for v in ticks) + 6; l += lw; b -= base * 1.5
    va = lambda v: b + (tp - b) * (v - lo) / (hi - lo)
    for v in ticks: add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="%s" stroke-width="0.5"/>' % (l, va(v), r, va(v), GRID)); t(l - 4, va(v) + base * 0.35, num(round(v, 10)), base, 'end')
    band = (r - l) / n; cats = max(sers, key=lambda s: len(s['cats']))['cats']; ud = any(g.find(C + 'upDownBars') is not None for g in groups) and len(sers) >= 4
    for i in range(n):
        x = l + band * (i + 0.5); col = [s['vals'][i] for s in sers if i < len(s['vals']) and s['vals'][i] is not None]; t(x, b + base * 1.2, cats[i] if i < len(cats) else '', base, 'middle')
        if not col: continue
        add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="#595959" stroke-width="1.2"/>' % (x, va(max(col)), x, va(min(col))))
        if ud:
            o, c = sers[0]['vals'][i], sers[-1]['vals'][i]
            if o is not None and c is not None:
                y0, y1 = sorted((va(o), va(c))); add('<rect x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s" stroke="#595959" stroke-width="0.8"/>' % (x - band * 0.2, y0, band * 0.4, max(y1 - y0, 0.8), '#fff' if c >= o else '#404040'))
        else:
            c = sers[-1]['vals'][i] if i < len(sers[-1]['vals']) else None
            if c is not None: add('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f" stroke="#595959" stroke-width="1.2"/>' % (x, va(c), x + band * 0.15, va(c)))
    add('<path d="M%.2f %.2f V%.2f H%.2f" fill="none" stroke="%s" stroke-width="0.75"/>' % (l, tp, b, r, AXIS))

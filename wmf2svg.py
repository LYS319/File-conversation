"""WMF(Windows 메타파일, MS-WMF 규격) -> 독립형 SVG 문자열. 순수 파이썬(PIL 은 비트맵 디코드에만).
HWP 문서 속 WMF 그림(오피스 클립아트·도면)을 `data:image/svg+xml` 로 넣기 위한 것 — PIL 은 리눅스에서 WMF 를 못 읽어 그림이 통째로 빠지고 쪽 수가 줄던 문제(hwp3-sample14 8쪽 대 11쪽)를 고친다.
rhwp 는 같은 일을 자체 변환기(src/wmf)로 하고 결과를 `data:image/svg+xml` 으로 넣는다(출력 형식만 참고, 코드는 가져오지 않았다 — MS-WMF 규격으로 직접 짰다). 지원: 선·다각형·여러 다각형·사각형·타원·둥근 사각형·글자(TextOut/ExtTextOut)·
DIB 비트맵(BitBlt/StretchDIBits)·펜·붓·글꼴·SaveDC/RestoreDC·창 좌표. 못 하는 것(건너뜀): 호/파이/코드, 해칭 붓 무늬, 래스터 연산(ROP) 합성, 영역 클리핑, 팔레트.
못 읽는 입력은 None. 시험: 코퍼스 WMF 27개 모두 변환(`test_hwpx_roundtrip.py` 의 'WMF→SVG')."""
import base64, io, math, struct
from html import escape

SRCCOPY = 0x00CC0020


def _color(c):
    return '#%02x%02x%02x' % (c & 0xFF, (c >> 8) & 0xFF, (c >> 16) & 0xFF)


def _dib_png(dib):
    """DIB(BITMAPINFOHEADER + 색표 + 픽셀) -> PNG 바이트. 못 읽으면 None."""
    try:
        from PIL import Image
        hs, = struct.unpack_from('<I', dib, 0)
        if hs == 12: bits, ncol, comp, bi = struct.unpack_from('<H', dib, 10)[0], 0, 0, 12
        else:
            bits, comp, ncol = struct.unpack_from('<HI', dib, 14)[0], struct.unpack_from('<I', dib, 16)[0], struct.unpack_from('<I', dib, 32)[0]
        pal = (ncol or (1 << bits)) * (3 if hs == 12 else 4) if bits <= 8 else (ncol * 4 if ncol else 0)
        masks = 12 if comp == 3 and hs == 40 else 0
        off = 14 + hs + pal + masks
        bmp = b'BM' + struct.pack('<IHHI', 14 + len(dib), 0, 0, off) + dib
        im = Image.open(io.BytesIO(bmp)); im.load(); im = im.convert('RGBA' if im.mode in ('RGBA', 'LA') else 'RGB')
        buf = io.BytesIO(); im.save(buf, 'PNG'); return buf.getvalue()
    except Exception:
        return None


class _DC:
    def __init__(s):
        s.pen = ('#000000', 1.0, 0); s.brush = ('#ffffff', 0); s.font = None
        s.text_color = '#000000'; s.bk_mode = 2; s.bk_color = '#ffffff'; s.align = 0; s.fill_mode = 1; s.pos = (0, 0)

    def copy(s):
        d = _DC(); d.__dict__.update(s.__dict__); return d


def wmf_to_svg(data):
    """WMF 바이트 -> SVG 문자열(실패하면 None)."""
    try:
        return _convert(data)
    except Exception:
        return None


def _convert(d):
    if len(d) < 18: return None
    placeable = d[:4] == bytes.fromhex('d7cdc69a')
    off0 = 22 if placeable else 0
    if placeable: pl, pt, pr, pb = struct.unpack_from('<hhhh', d, 6)
    if struct.unpack_from('<H', d, off0 + 2)[0] != 9: return None      # 표준 WMF 머리 크기
    i = off0 + 18
    objs = {}; dc = _DC(); stack = []
    win = {'ox': 0, 'oy': 0, 'ex': None, 'ey': None}; seen = {'ex': False}
    out = []; pts_all = []

    def free_slot():
        k = 0
        while k in objs: k += 1
        return k

    def X(x): return x - win['ox']
    def Y(y): return y - win['oy']
    def P(x, y): pts_all.append((x, y)); return '%g,%g' % (X(x), Y(y))

    def stroke():
        col, w, st = dc.pen
        if st == 5: return 'stroke="none"'      # PS_NULL
        a = 'stroke="%s" stroke-width="%g"' % (col, max(w, 1))
        dash = {1: '6,3', 2: '2,2', 3: '6,2,2,2', 4: '6,2,2,2,2,2'}.get(st)
        return a + (' stroke-dasharray="%s"' % dash if dash else '') + ' stroke-linejoin="round"'

    def fill():
        col, st = dc.brush
        return 'fill="none"' if st == 1 or col is None else 'fill="%s"' % col

    while i + 6 <= len(d):
        size, fn = struct.unpack_from('<IH', d, i)
        if size < 3 or i + size * 2 > len(d): break
        p = d[i + 6:i + size * 2]; i += size * 2
        if fn == 0x0000: break
        if fn == 0x020B: win['oy'], win['ox'] = struct.unpack_from('<hh', p)      # SetWindowOrg: 매개변수는 거꾸로(Y, X)
        elif fn == 0x020C:
            if not seen['ex']: win['ey'], win['ex'] = struct.unpack_from('<hh', p); seen['ex'] = True
        elif fn == 0x0102: dc.bk_mode, = struct.unpack_from('<H', p)
        elif fn == 0x0201: dc.bk_color = _color(struct.unpack_from('<I', p)[0])
        elif fn == 0x0209: dc.text_color = _color(struct.unpack_from('<I', p)[0])
        elif fn == 0x012E: dc.align, = struct.unpack_from('<H', p)
        elif fn == 0x0106: dc.fill_mode, = struct.unpack_from('<H', p)
        elif fn == 0x02FA:      # CreatePenIndirect: 종류, 굵기(PointS), 색
            st, w, _h, col = struct.unpack_from('<HhhI', p); objs[free_slot()] = ('pen', _color(col), float(w), st & 0xF)
        elif fn == 0x02FC:      # CreateBrushIndirect: 종류, 색, 해칭
            st, col, _hatch = struct.unpack_from('<HIH', p); objs[free_slot()] = ('brush', _color(col) if st in (0, 2) else None, 1 if st == 1 else 0)
        elif fn == 0x02FB:      # CreateFontIndirect
            h, w, esc, ori, wt = struct.unpack_from('<hhhhh', p); it, ul, so, cs = p[10], p[11], p[12], p[13]
            name = p[18:50].split(b'\0')[0]
            try: face = name.decode('cp949' if cs in (129, 1, 0) else 'latin-1')
            except Exception: face = name.decode('latin-1', 'replace')
            objs[free_slot()] = ('font', h, wt, esc, it, ul, so, cs, face)
        elif fn in (0x00F7, 0x0142, 0x01F9, 0x06FF): objs[free_slot()] = ('other',)      # 팔레트·무늬 붓·영역: 자리만 차지
        elif fn == 0x012D:
            o = objs.get(struct.unpack_from('<H', p)[0])
            if o and o[0] == 'pen': dc.pen = (o[1], o[2], o[3])
            elif o and o[0] == 'brush': dc.brush = (o[1], o[2])
            elif o and o[0] == 'font': dc.font = o
        elif fn == 0x01F0: objs.pop(struct.unpack_from('<H', p)[0], None)
        elif fn == 0x001E: stack.append(dc.copy())
        elif fn == 0x0127:
            n, = struct.unpack_from('<h', p)
            for _ in range(min(abs(n), len(stack))): dc = stack.pop()
        elif fn in (0x0324, 0x0325):      # Polygon / Polyline
            n, = struct.unpack_from('<H', p); pts = struct.unpack_from('<%dh' % (2 * n), p, 2)
            s = ' '.join(P(pts[2 * k], pts[2 * k + 1]) for k in range(n))
            if fn == 0x0324: out.append('<polygon points="%s" %s %s fill-rule="%s"/>' % (s, fill(), stroke(), 'evenodd' if dc.fill_mode == 1 else 'nonzero'))
            else: out.append('<polyline points="%s" fill="none" %s/>' % (s, stroke()))
        elif fn == 0x0538:      # PolyPolygon
            n, = struct.unpack_from('<H', p); counts = struct.unpack_from('<%dH' % n, p, 2); q = 2 + 2 * n; dd = []
            for c in counts:
                pts = struct.unpack_from('<%dh' % (2 * c), p, q); q += 4 * c
                dd.append('M' + ' L'.join(P(pts[2 * k], pts[2 * k + 1]) for k in range(c)) + 'Z')
            out.append('<path d="%s" %s %s fill-rule="%s"/>' % (' '.join(dd), fill(), stroke(), 'evenodd' if dc.fill_mode == 1 else 'nonzero'))
        elif fn in (0x041B, 0x0418, 0x061C):      # Rectangle / Ellipse / RoundRect (거꾸로: 아래·오른쪽·위·왼쪽)
            if fn == 0x061C: rh, rw, b, r, t, l = struct.unpack_from('<hhhhhh', p)
            else: b, r, t, l = struct.unpack_from('<hhhh', p); rh = rw = 0
            if r < l: l, r = r, l
            if b < t: t, b = b, t
            P(l, t); P(r, b)
            if fn == 0x0418: out.append('<ellipse cx="%g" cy="%g" rx="%g" ry="%g" %s %s/>' % (X((l + r) / 2), Y((t + b) / 2), (r - l) / 2, (b - t) / 2, fill(), stroke()))
            else: out.append('<rect x="%g" y="%g" width="%g" height="%g" rx="%g" ry="%g" %s %s/>' % (X(l), Y(t), r - l, b - t, rw / 2, rh / 2, fill(), stroke()))
        elif fn == 0x0214: dc.pos = struct.unpack_from('<hh', p)[::-1]      # MoveTo(Y, X)
        elif fn == 0x0213:      # LineTo
            y, x = struct.unpack_from('<hh', p)
            out.append('<line x1="%g" y1="%g" x2="%g" y2="%g" fill="none" %s/>' % (X(dc.pos[0]), Y(dc.pos[1]), X(x), Y(y), stroke())); P(dc.pos[0], dc.pos[1]); P(x, y); dc.pos = (x, y)
        elif fn in (0x0521, 0x0A32):      # TextOut / ExtTextOut
            if fn == 0x0521:
                n, = struct.unpack_from('<H', p); raw = p[2:2 + n]; yy, xx = struct.unpack_from('<hh', p, 2 + n + (n & 1)); dx = None
            else:
                yy, xx, n, opts = struct.unpack_from('<hhHH', p); q = 8 + (8 if opts & 6 else 0); raw = p[q:q + n]; q += n + (n & 1)
                dx = list(struct.unpack_from('<%dh' % n, p, q)) if opts & 0x100 == 0 and len(p) >= q + 2 * n else None
            out.append(_text(dc, raw, xx, yy, dx, X, Y, P))
        elif fn in (0x0940, 0x0F43, 0x0B41):      # DibBitBlt / StretchDIBits / DibStretchBlt
            im = _bitmap(fn, p)
            if im:
                png, (dx_, dy_, dw, dh) = im; P(dx_, dy_); P(dx_ + dw, dy_ + dh)
                out.append('<image x="%g" y="%g" width="%g" height="%g" preserveAspectRatio="none" href="data:image/png;base64,%s"/>' % (X(min(dx_, dx_ + dw)), Y(min(dy_, dy_ + dh)), abs(dw), abs(dh), base64.b64encode(png).decode()))
    if not out: return None
    if win['ex'] and win['ey']: w, h = abs(win['ex']), abs(win['ey'])
    elif placeable: w, h = abs(pr - pl), abs(pb - pt)
    else:
        xs = [X(x) for x, _ in pts_all]; ys = [Y(y) for _, y in pts_all]
        if not xs: return None
        w, h = max(xs), max(ys)
    if w <= 0 or h <= 0: return None
    return ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 %g %g" width="%g" height="%g" preserveAspectRatio="none">%s</svg>' % (w, h, w, h, ''.join(out)))


def _text(dc, raw, x, y, dx, X, Y, P):
    f = dc.font
    h, wt, esc, it, ul, so, cs, face = (f[1], f[2], f[3], f[4], f[5], f[6], f[7], f[8]) if f else (-12, 400, 0, 0, 0, 0, 0, '')
    em = abs(h) if h < 0 else abs(h) / 1.15      # 높이: 음수=글자 높이, 양수=줄 높이(글자+여백)
    try: s = raw.decode('cp949')
    except Exception: s = raw.decode('latin-1')
    s = s.replace('\0', '')
    if not s.strip(): return ''
    a = dc.align
    anchor = 'end' if (a & 6) == 2 else 'middle' if (a & 6) == 6 else 'start'
    if (a & 24) == 24: by = y      # TA_BASELINE
    elif a & 8: by = y - em * 0.2      # TA_BOTTOM
    else: by = y + em * 0.86      # TA_TOP: 줄 윗선에서 글자 기준선까지
    P(x, y); P(x, y + em)
    attrs = 'font-size="%g" fill="%s"' % (em, dc.text_color)
    if face: attrs += ' font-family="%s"' % escape("'%s',sans-serif" % face.replace("'", ''), quote=True)
    if wt >= 600: attrs += ' font-weight="700"'
    if it: attrs += ' font-style="italic"'
    if ul or so: attrs += ' text-decoration="%s"' % ' '.join(k for k, v in (('underline', ul), ('line-through', so)) if v)
    xs = ''
    if dx and len(dx) == len(s) and anchor == 'start':      # 글자마다 앞선 폭(Dx 배열)이 있으면 글자별 x
        acc = 0; lst = []
        for v in dx: lst.append('%g' % X(x + acc)); acc += v
        xs = ' '.join(lst)
    tr = ' transform="rotate(%g %g %g)"' % (-esc / 10, X(x), Y(by)) if esc else ''
    return '<text x="%s" y="%g" text-anchor="%s" xml:space="preserve" %s%s>%s</text>' % (xs or '%g' % X(x), Y(by), anchor, attrs, tr, escape(s))


def _bitmap(fn, p):
    """BitBlt 계열 레코드 -> (PNG, (목적 x, y, 폭, 높이)) 또는 None. 래스터 연산은 SRCCOPY 만 그린다."""
    if fn == 0x0F43:      # StretchDIBits: ROP(4) 사용(2) 원본 높이·폭·y·x, 목적 높이·폭·y·x, DIB
        rop, _cu, sh, sw, sy, sx, dh, dw, dy, dx_ = struct.unpack_from('<IHhhhhhhhh', p); dib = p[22:]
    elif fn == 0x0940:      # DibBitBlt: ROP(4) 원본 y·x, 높이·폭, 목적 y·x, DIB(없을 수 있음)
        rop, sy, sx, dh, dw, dy, dx_ = struct.unpack_from('<Ihhhhhh', p); dib = p[16:]
        if len(dib) < 40: return None
    else:      # DibStretchBlt: ROP(4) 원본 높이·폭·y·x, 목적 높이·폭·y·x, DIB
        rop, sh, sw, sy, sx, dh, dw, dy, dx_ = struct.unpack_from('<Ihhhhhhhh', p); dib = p[20:]
    if rop != SRCCOPY or len(dib) < 12: return None
    png = _dib_png(dib)
    return (png, (dx_, dy, dw, dh)) if png else None


MAX_SVG_BYTES = 20 * 1024 * 1024


def vector_svg(data, ext=''):
    """BinData 바이트가 벡터 그림이면 SVG 문자열, 아니면(또는 못 읽거나 위험하면) None. 지원: WMF(변환), SVG(그대로).
    SVG 는 `<!ENTITY`(엔티티 폭탄·외부 개체)·`<script`·`<foreignObject`·외부 주소 참조가 있으면 거절한다. 그림은 `<img src="data:image/svg+xml;base64,…">` 로만 쓰여
    브라우저·WeasyPrint 모두 스크립트를 돌리지 않고 `data:` 밖 주소도 안 연다(convert._to_pdf 의 URLFetcher)."""
    ext = (ext or '').lower().lstrip('.')
    if data[:4] == bytes.fromhex('d7cdc69a') or (ext == 'wmf' and data[:2] in (bytes.fromhex('0100'), bytes.fromhex('0200'))):
        return wmf_to_svg(data)
    head = data[:256].lstrip(bytes.fromhex('efbbbf20090d0a'))
    if ext == 'svg' or head.startswith((b'<svg', b'<?xml')) and b'<svg' in data[:4096]:
        if len(data) > MAX_SVG_BYTES: return None
        t = data.decode('utf-8', 'replace')
        low = t.lower()
        if any(k in low for k in ('<!entity', '<script', '<foreignobject')) or 'href="http' in low or "href='http" in low: return None
        return t
    return None

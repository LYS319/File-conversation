"""HTML (inline-CSS) -> HWPX. Reads ONLY the HTML file."""
import sys, re, zipfile, base64, io, html as H
import lxml.html
from lxml import etree
from PIL import Image

MEDIA = {'jpeg': ('jpg', 'image/jpeg'), 'png': ('png', 'image/png'), 'gif': ('gif', 'image/gif'), 'bmp': ('bmp', 'image/bmp')}
MAX_IMG_BYTES = 100 * 1024 * 1024

def parse_css(st):
    out = {}
    for part in (st or '').split(';'):
        if ':' in part:
            k, v = part.split(':', 1); out[k.strip().lower()] = v.strip()
    return out
def length(v, base_pt=None):
    """CSS length -> HWPUNIT"""
    v = v.strip()
    m = re.match(r'(-?[\d.]+)\s*(pt|px|mm|cm|in|em)?', v)
    if not m: return 0
    n, u = float(m.group(1)), (m.group(2) or 'px')
    f = {'pt':100, 'px':75, 'mm':7200/25.4, 'cm':72000/25.4, 'in':7200}.get(u)
    if u == 'em': return round(n * (base_pt or 10) * 100)
    return round(n * f)
def wlen(v, ref):
    """width: '%'는 ref(HWPUNIT) 기준으로, 그 밖에는 length()로"""
    v = v.strip()
    return round(float(v[:-1]) / 100 * ref) if v.endswith('%') else length(v)
def inline_style_rules(doc):
    """<style>의 tag / .class / tag.class 규칙(자손·자식 결합자 포함)을 style 속성으로 풀어 넣는다. 요소 자신의 style이 우선.
    # ponytail: #id·[attr]·:pseudo 선택자는 건너뜀. 필요해지면 css-inline 같은 라이브러리로 교체"""
    css = re.sub(r'/\*.*?\*/', '', ''.join(st.text or '' for st in doc.iter('style')), flags=re.S)
    css = re.sub(r'@[\w-]+[^{}]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}', '', css)      # @page / @media 제외
    rules = []
    for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
        for sel in m.group(1).split(','):
            toks = re.findall(r'>|[^\s>]+', sel.strip())
            if not toks or any(re.search(r'[#\[:]', t) for t in toks): continue
            xp, spec, comb = '', 0, '//'
            for t in toks:
                if t == '>': comb = '/'; continue
                cls = re.findall(r'\.([\w-]+)', t); tag = re.match(r'[\w*-]*', t).group() or '*'
                xp += comb + tag + ''.join(f"[contains(concat(' ',normalize-space(@class),' '),' {c} ')]" for c in cls)
                spec += 10 * len(cls) + (tag != '*'); comb = '//'
            rules.append((spec, len(rules), xp, m.group(2)))
    decl = {}
    for spec, order, xp, body in rules:
        for el in doc.xpath(xp): decl.setdefault(el, []).append((spec, order, body))
    for el, lst in decl.items():
        merged = {}
        for _, _, body in sorted(lst, key=lambda x: x[:2]): merged.update(parse_css(body))
        merged.update(parse_css(el.get('style')))
        el.set('style', ';'.join(f'{k}:{v}' for k, v in merged.items()))
def est_height(td, w, img_h=None):
    """높이 지정이 없는 셀이 글자 수만큼 필요로 하는 높이(HWPUNIT)를 어림한다. LibreOffice/H2Orestart가 cellSz 높이를 고정값으로 써서 안 넣으면 잘린다.
    # ponytail: 전각 1em·반각 0.5em로 줄 수를 어림한 값. 정확한 줄바꿈이 아니라 넉넉한 쪽으로 틀린다. 글꼴 폭 측정으로 교체 가능"""
    css = parse_css(td.get('style'))
    total = 283                                                   # 위아래 안쪽 여백
    for p in td.xpath('.//p') or [td]:
        pc = {**css, **parse_css(p.get('style'))}
        base = length(pc['font-size']) if 'font-size' in pc else 1000
        runs = [(p.text or '', base)]                               # (글자, 크기): 크기는 span이 지정하는 경우가 많다
        for e in p:
            if isinstance(e.tag, str):
                st = parse_css(e.get('style'))
                runs.append((e.text_content(), length(st['font-size']) if 'font-size' in st else base))
            runs.append((e.tail or '', base))
        n = sum(len(t) for t, _ in runs)
        fs = sum(len(t) * f for t, f in runs) / n if n else base     # 글자 수 가중 평균 크기
        lh = pc.get('line-height', '1.6')
        lh = float(lh) if re.match(r'^[\d.]+$', lh) else (length(lh) / fs if lh.endswith(('pt', 'px')) else 1.6)
        cw = sum(f if ord(c) >= 0x2E80 else f / 2 for t, f in runs for c in t)
        avail = max(w - 1020 - length(pc.get('padding-left', '0')), fs)
        lines = max(1, -(-int(cw) // avail)) + len(p.xpath('.//br'))
        total += round(lines * fs * lh)       # 한컴이 계산한 원본 셀 높이(회의록 본문 칸 47845)와 3% 안쪽. H2Orestart 줄 간격에 맞춘 0.9 보정은 한컴 기준에선 모자라 폐기
    for im in td.xpath('.//img') if img_h else []: total += img_h(im, w - 1020)      # 그림은 표시 높이만큼 더 필요(원본 사진 칸 18880 ≈ 그림 17094 + 줄 1건)
    return total
def color(v):
    v = v.strip().lower()
    named = {'black':'#000000','white':'#FFFFFF','red':'#FF0000','blue':'#0000FF','green':'#008000','gray':'#808080','grey':'#808080','yellow':'#FFFF00'}
    if v in named: return named[v]
    m = re.match(r'#([0-9a-f]{3})$', v)
    if m: return '#' + ''.join(c*2 for c in m.group(1)).upper()
    m = re.match(r'#([0-9a-f]{6})', v)
    if m: return '#' + m.group(1).upper()
    m = re.match(r'rgba?\((\d+),\s*(\d+),\s*(\d+)', v)
    if m: return '#%02X%02X%02X' % tuple(int(x) for x in m.groups())
    return None
GENERIC = {'serif','sans-serif','monospace','cursive','fantasy','system-ui'}
def families(v):
    return [f.strip().strip('\'"') for f in v.split(',') if f.strip().strip('\'"') and f.strip().strip('\'"').lower() not in GENERIC]
BORDER = {'solid':'SOLID','dashed':'DASH','dotted':'DOT','double':'DOUBLE_SLIM','none':'NONE','hidden':'NONE'}
HWP_WIDTHS = [0.1,0.12,0.15,0.2,0.25,0.3,0.4,0.5,0.6,0.7,1.0,1.5,2.0,3.0,4.0,5.0]
def border(v):
    if not v or v.split()[0] in ('none','hidden','0'): return ('NONE','0.1 mm','#000000')
    t, w, c = 'SOLID', 0.12, '#000000'
    for tok in re.split(r'\s+(?![^()]*\))', v.strip()):
        if tok in BORDER: t = BORDER[tok]
        elif re.match(r'[\d.]+(mm|pt|px|cm)?$', tok): w = length(tok) / (7200/25.4)
        elif color(tok): c = color(tok)
    w = min(HWP_WIDTHS, key=lambda x: abs(x - w))
    return (t, f'{w:g} mm', c)

CHAR_KEYS = ('font-family','font-size','color','font-weight','font-style','text-decoration','letter-spacing','font-stretch','vertical-align','background-color')
ALIGN = {'justify':'JUSTIFY','left':'LEFT','start':'LEFT','right':'RIGHT','end':'RIGHT','center':'CENTER'}
LANGS = ['HANGUL','LATIN','HANJA','JAPANESE','OTHER','SYMBOL','USER']

def is_half(ch):
    """half-width glyph (Latin, digits, punctuation, space): HWP 자간 % applies to ~0.5em width"""
    o = ord(ch)
    return o < 0x2E80 and not (0x1100 <= o <= 0x11FF) and o != 0x2007 or ch in ' \t'

class Builder:
    def __init__(s):
        s.fonts = []                     # face list (same list for every language)
        s.charPrs = []; s.paraPrs = []; s.borderFills = []
        s.bf_index = {}
        s.bf((('NONE','0.1 mm','#000000'),)*4 + (None,))      # id 1: page border
        s.bf((('NONE','0.1 mm','#000000'),)*4 + ('none',))    # id 2: char / paragraph default
        s.pid = 0; s.oid = 1000000000; s.z = 0
        s.content_w = 48100            # 본문 폭(HWPUNIT). build()가 페이지 설정으로 덮어씀
        s.avail_w = None               # 지금 들어 있는 표 칸의 안쪽 폭(HWPUNIT). 이미지가 이 폭을 넘지 않게 줄이는 데 씀
        s.bins = []                    # (파일명, 바이트, media-type): BinData로 저장할 이미지
    def font(s, f):
        if f not in s.fonts: s.fonts.append(f)
        return s.fonts.index(f)
    def bf(s, key):
        if key not in s.bf_index:
            s.borderFills.append(key); s.bf_index[key] = len(s.borderFills)   # ids start at 1
        return s.bf_index[key]

    # ---------- styles ----------
    def char_id(s, css, text=None):
        size = length(css.get('font-size', '10pt'))
        fam = families(css.get('font-family', "'함초롬바탕'")) or ['함초롬바탕']
        han = s.font(fam[0]); lat = s.font(fam[1] if len(fam) > 1 else fam[0])
        deco = css.get('text-decoration', '')
        ls = css.get('letter-spacing', '0')
        half = bool(text) and all(is_half(ch) for ch in text)
        sp = round(float(ls[:-2]) * (200 if half else 100)) if ls.endswith('em') else round(length(ls) / max(size, 1) * 100) if ls not in ('0', 'normal') else 0
        fs = css.get('font-stretch', '100%')
        ratio = int(float(fs[:-1])) if fs.endswith('%') else 100
        va = css.get('vertical-align', '')
        key = (size, han, lat, color(css.get('color', '#000000')) or '#000000',
               css.get('font-weight', '') in ('bold','bolder','600','700','800','900'), css.get('font-style', '') == 'italic',
               'underline' in deco, 'line-through' in deco, max(-50, min(50, sp)), ratio,
               'super' if va == 'super' else 'sub' if va == 'sub' else '',
               color(css['background-color']) if 'background-color' in css else None)
        if key not in s.charPrs: s.charPrs.append(key)
        return s.charPrs.index(key)
    def para_id(s, css, base_size):
        padl = length(css.get('padding-left', '0')); ind = length(css.get('text-indent', '0'), base_size)
        lh = css.get('line-height', '1.6')
        if re.match(r'^[\d.]+$', lh): ls = ('PERCENT', round(float(lh) * 100))
        elif lh.endswith('%'): ls = ('PERCENT', round(float(lh[:-1])))
        elif lh == 'normal': ls = ('PERCENT', 120)
        else: ls = ('FIXED', length(lh))
        fill = color(css['background-color']) if 'background-color' in css else None
        key = (ALIGN.get(css.get('text-align', 'justify'), 'JUSTIFY'),
               padl + min(ind, 0), ind, length(css.get('padding-right', '0')),
               max(0, length(css.get('margin-top', '0'))), max(0, length(css.get('margin-bottom', '0'))), ls,   # 음수 여백은 HWPX 에 없다(hwpx2html 이 칸 안 첫·끝 문단에 넣는다)
               s.bf((('NONE','0.1 mm','#000000'),)*4 + (fill or 'none',)) if fill else 2,
               'BREAK_WORD' if css.get('word-break') == 'break-all' else 'KEEP_WORD')
        if key not in s.paraPrs: s.paraPrs.append(key)
        return s.paraPrs.index(key)

    # ---------- content ----------
    def img_size(s, img, css, ref):
        """(바이트, PIL 이미지, 표시 폭, 표시 높이[HWPUNIT]). data URI가 아니면 None. 폭이 ref(칸·본문 폭)를 넘으면 비율을 지켜 줄인다."""
        m = re.match(r'data:image/[\w.+-]+;base64,(.*)$', img.get('src') or '', re.S)
        if not m: return None
        data = base64.b64decode(m.group(1))
        if len(data) > MAX_IMG_BYTES: raise ValueError('이미지가 너무 큼')
        im = Image.open(io.BytesIO(data)); pw, ph = im.size
        if pw * ph > 100_000_000: raise ValueError('이미지 해상도가 너무 큼')
        dim = lambda v: wlen(v, ref) if v and v.strip() not in ('auto', 'inherit', 'initial') else None      # height:auto 등은 지정 없음
        w = dim(css.get('width') or img.get('width')); h = dim(css.get('height') or img.get('height'))
        if w is None and h is None: w = pw * 75                  # 96dpi 픽셀 1개 = 75 HWPUNIT
        if w is None: w = round(h * pw / ph)
        if h is None: h = round(w * ph / pw)
        if w > ref: h = round(h * ref / w); w = ref
        return data, im, max(w, 100), max(h, 100)

    def picture(s, img, css):
        """<img src="data:image/...">를 BinData로 저장하고 hp:pic XML을 돌려준다. data URI가 아니면 None.
        외부 URL·파일 경로는 가져오지 않는다(SSRF·로컬 파일 노출 방지). 구조는 hwp-cli가 만든 HWPX(validate 통과)를 기준으로 함.
        # ponytail: data URI만 지원. 필요하면 허용 목록 방식으로 http(s)를 열 수 있음"""
        r = s.img_size(img, css, s.avail_w or s.content_w)
        if not r: return None
        data, im, w, h = r; fmt = (im.format or '').lower()
        if fmt not in MEDIA:                                     # webp 등 한글이 모르는 형식은 PNG로
            buf = io.BytesIO(); im.save(buf, 'PNG'); data, fmt = buf.getvalue(), 'png'
        ext, mime = MEDIA[fmt]
        s.bins.append((f'image{len(s.bins) + 1}.{ext}', data, mime)); n = len(s.bins)
        s.oid += 1; s.z += 1
        alt = H.escape(img.get('alt') or '', quote=False)
        return (f'<hp:pic id="{s.oid}" zOrder="{s.z}" numberingType="PICTURE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" href="" groupLevel="0" instid="{s.oid}" reverse="0">'
                f'<hp:offset x="0" y="0"/><hp:orgSz width="{w}" height="{h}"/><hp:curSz width="{w}" height="{h}"/><hp:flip horizontal="0" vertical="0"/>'
                f'<hp:rotationInfo angle="0" centerX="{w // 2}" centerY="{h // 2}" rotateimage="1"/>'
                '<hp:renderingInfo><hc:transMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/><hc:scaMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/><hc:rotMatrix e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"/></hp:renderingInfo>'
                f'<hc:img binaryItemIDRef="image{n}" bright="0" contrast="0" effect="REAL_PIC" alpha="0"/>'
                f'<hp:imgRect><hc:pt0 x="0" y="0"/><hc:pt1 x="{w}" y="0"/><hc:pt2 x="{w}" y="{h}"/><hc:pt3 x="0" y="{h}"/></hp:imgRect>'
                f'<hp:imgClip left="0" right="{w}" top="0" bottom="{h}"/><hp:inMargin left="0" right="0" top="0" bottom="0"/><hp:imgDim dimwidth="{w}" dimheight="{h}"/>'
                f'<hp:sz width="{w}" widthRelTo="ABSOLUTE" height="{h}" heightRelTo="ABSOLUTE" protect="0"/>'
                '<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
                '<hp:outMargin left="0" right="0" top="0" bottom="0"/>'
                + (f'<hp:shapeComment>{alt}</hp:shapeComment>' if alt else '') + '</hp:pic>')

    def inline_runs(s, node, css, runs):
        """walk inline content; produce list of (charId, [text | 'BR' | ('TBL', xml)])"""
        def add(cid, item):
            if runs and runs[-1][0] == cid and not isinstance(item, tuple) and not (runs[-1][1] and isinstance(runs[-1][1][-1], tuple)):
                runs[-1][1].append(item)
            else: runs.append((cid, [item]))
        if node.text: add(s.char_id(css, node.text), node.text)
        for ch in node:
            if not isinstance(ch.tag, str):
                if ch.tail: add(s.char_id(css, ch.tail), ch.tail)
                continue
            tag = ch.tag.lower()
            ccss = {k: v for k, v in css.items() if k in CHAR_KEYS and k != 'background-color'}
            ccss.update({k: v for k, v in parse_css(ch.get('style')).items()})
            if tag == 'br': add(s.char_id(css), 'BR')
            elif tag == 'table': add(s.char_id(css), ('TBL', s.table(ch)))
            elif tag == 'img':
                pic = s.picture(ch, ccss)
                if pic: add(s.char_id(css), ('PIC', pic))
                elif ch.get('alt'): add(s.char_id(css, ch.get('alt')), ch.get('alt'))
            elif tag in ('b', 'strong'): ccss['font-weight'] = 'bold'; s.inline_runs(ch, ccss, runs)
            elif tag in ('i', 'em'): ccss['font-style'] = 'italic'; s.inline_runs(ch, ccss, runs)
            elif tag == 'u': ccss['text-decoration'] = 'underline'; s.inline_runs(ch, ccss, runs)
            elif tag == 'sup': ccss['vertical-align'] = 'super'; s.inline_runs(ch, ccss, runs)
            elif tag == 'sub': ccss['vertical-align'] = 'sub'; s.inline_runs(ch, ccss, runs)
            else: s.inline_runs(ch, ccss, runs)
            if ch.tail: add(s.char_id(css, ch.tail), ch.tail)
        return runs

    def paragraph(s, node, inherited, first=False, secpr=''):
        css = dict(inherited); css.update(parse_css(node.get('style')))
        base = length(css.get('font-size', '10pt')) / 100
        pp = s.para_id(css, base)
        charcss = {k: v for k, v in css.items() if k in CHAR_KEYS and k != 'background-color'}
        runs = s.inline_runs(node, charcss, [])
        # a lone trailing <br> (empty paragraph marker / trailing br) is not a line break in HTML rendering
        if runs and runs[-1][1] and runs[-1][1][-1] == 'BR':
            runs[-1][1].pop()
            if not runs[-1][1]: runs.pop()
        if not runs: runs = [(s.char_id(charcss), [])]
        brk = '1' if css.get('break-before') == 'page' or css.get('page-break-before') == 'always' else '0'
        s.pid += 1
        out = [f'<hp:p id="{s.pid}" paraPrIDRef="{pp}" styleIDRef="0" pageBreak="{brk}" columnBreak="0" merged="0">']
        for i, (cid, items) in enumerate(runs):
            out.append(f'<hp:run charPrIDRef="{cid}">' + (secpr if first and i == 0 else ''))
            t = ''
            def flush_t():
                nonlocal t
                if t: out.append(f'<hp:t>{t}</hp:t>'); t = ''
            for it in items:
                if isinstance(it, tuple): flush_t(); out.append(it[1])
                elif it == 'BR': t += '<hp:lineBreak/>'
                else:
                    txt = H.escape(it, quote=False)
                    txt = txt.replace('\u2007', '<hp:fwSpace/>').replace('\t', '<hp:tab width="4000" leader="0" type="1"/>')
                    t += txt
            flush_t()
            if not items: out.append('<hp:t/>')
            out.append('</hp:run>')
        out.append('</hp:p>')
        return ''.join(out)

    def blocks(s, node, inherited, secpr=''):
        """block container -> list of paragraph xml"""
        out = []
        css = dict(inherited); css.update({k: v for k, v in parse_css(node.get('style')).items() if k in CHAR_KEYS and k != 'background-color'})
        loose = []   # inline content directly in a container
        def flush_loose():
            if loose:
                tmp = lxml.html.fromstring('<p></p>'); 
                for x in loose: tmp.append(x)
                out.append(s.paragraph(tmp, css, first=not out and bool(secpr), secpr=secpr)); loose.clear()
        if node.text and node.text.strip(): 
            out.append(s.paragraph(lxml.html.fromstring(f'<p>{H.escape(node.text)}</p>'), css, first=not out and bool(secpr), secpr=secpr))
        for ch in node:
            if not isinstance(ch.tag, str): continue
            tag = ch.tag.lower()
            is_container = tag in ('div','section','article','figure','blockquote','li','ul','ol','body') and \
                any(isinstance(g.tag, str) and g.tag.lower() in ('p','div','h1','h2','h3','h4','h5','h6','ul','ol','li','section') for g in ch)
            if tag in ('p','h1','h2','h3','h4','h5','h6') or (tag in ('div', 'figure') and not is_container):
                flush_loose(); out.append(s.paragraph(ch, css, first=not out and bool(secpr), secpr=secpr))
            elif is_container:
                flush_loose(); sub = s.blocks(ch, css, secpr if not out else '')
                out += sub
            elif tag == 'table':
                flush_loose(); wrap = lxml.html.fromstring('<div></div>'); 
                import copy; wrap.append(copy.deepcopy(ch))
                out.append(s.paragraph(wrap, css, first=not out and bool(secpr), secpr=secpr))
            elif tag in ('style','script','title','meta','head'): continue
            else: loose.append(ch)
            if ch.tail and ch.tail.strip(): pass
        flush_loose()
        if not out: out.append(s.paragraph(lxml.html.fromstring('<p></p>'), css, first=bool(secpr), secpr=secpr))
        return out

    def table(s, t):
        tcss = parse_css(t.get('style'))
        total = wlen(tcss['width'], s.content_w) if 'width' in tcss else s.content_w
        cols = [wlen(parse_css(c.get('style')).get('width', c.get('width', '0')), total) for c in t.iter('col')]
        rows = [tr for tr in t.iter('tr') if tr.getparent() is t or tr.getparent().getparent() is t]
        # grid placement (handles colspan/rowspan)
        occ = set(); cells = []
        for r, tr in enumerate(rows):
            c = 0
            for td in tr:
                if not isinstance(td.tag, str) or td.tag.lower() not in ('td', 'th'): continue
                while (r, c) in occ: c += 1
                cs, rs = int(td.get('colspan', 1)), int(td.get('rowspan', 1))
                for dr in range(rs):
                    for dc in range(cs): occ.add((r + dr, c + dc))
                cells.append(dict(td=td, r=r, c=c, cs=cs, rs=rs, css=parse_css(td.get('style'))))
                c += cs
        ncol = max(c for _, c in occ) + 1; nrow = len(rows)
        if len(cols) != ncol:  # derive columns from single-span cell widths
            cols = [0] * ncol
            for x in cells:
                if x['cs'] == 1 and 'width' in x['css']: cols[x['c']] = max(cols[x['c']], wlen(x['css']['width'], total))
            miss = [i for i, w in enumerate(cols) if not w]
            for i in miss: cols[i] = max((total - sum(cols)) // len(miss), 1000)
        rowh = [0] * nrow
        for x in cells:
            if x['rs'] == 1:
                h = length(x['css']['height']) if 'height' in x['css'] else est_height(x['td'], sum(cols[x['c']:x['c'] + x['cs']]), lambda im, ref: (s.img_size(im, parse_css(im.get('style')), ref) or (0, 0, 0, 0))[3])
                rowh[x['r']] = max(rowh[x['r']], h)
        rowh = [h or 1500 for h in rowh]
        trs = []
        for r in range(nrow):
            tcs = []
            for x in [x for x in cells if x['r'] == r]:
                css = x['css']; w = sum(cols[x['c']:x['c'] + x['cs']]); h = length(css['height']) if 'height' in css else sum(rowh[x['r']:x['r'] + x['rs']])
                pad = css.get('padding', '1.41pt 5.1pt').split()
                pad = [length(p) for p in (pad * 4)[:4]] if len(pad) != 2 else [length(pad[0]), length(pad[1])] * 2
                if len(css.get('padding', '').split()) == 3:
                    p3 = [length(p) for p in css['padding'].split()]; pad = [p3[0], p3[1], p3[2], p3[1]]
                for i, side in enumerate(('top','right','bottom','left')):
                    if f'padding-{side}' in css: pad[i] = length(css[f'padding-{side}'])
                default_b = css.get('border', '')
                bkey = tuple(border(css.get(f'border-{sd}', default_b)) for sd in ('left','right','top','bottom'))
                fill = color(css['background-color']) if 'background-color' in css else (color(css['background']) if 'background' in css else None)
                diag = None
                for m in re.finditer(r'linear-gradient\(\s*to (top|bottom) right\s*,[^,]*,\s*(#[0-9a-fA-F]{3,6}|rgba?\([^)]*\)|\w+)\s+calc\(50%\s*-\s*([\d.]+)(mm|pt|px)\)', css.get('background-image', '')):
                    kind = 'backSlash' if m.group(1) == 'top' else 'slash'
                    wmm = length(m.group(3) + m.group(4)) * 2 / (7200 / 25.4)
                    wmm = min(HWP_WIDTHS, key=lambda x: abs(x - wmm))
                    diag = (tuple(sorted(set((diag or ((),))[0]) | {kind})), f'{wmm:g} mm', color(m.group(2)) or '#000000')
                bfid = s.bf(bkey + (fill or 'none',) + ((diag,) if diag else ()))
                va = {'top':'TOP','middle':'CENTER','bottom':'BOTTOM'}.get(css.get('vertical-align', 'top'), 'TOP')
                outer_w, s.avail_w = s.avail_w, max(w - pad[1] - pad[3], 1000)
                inner = ''.join(s.blocks(x['td'], {}))
                s.avail_w = outer_w
                tcs.append(f'<hp:tc name="" header="{int(rows[x["r"]].getparent().tag == "thead")}" hasMargin="1" protect="0" editable="0" dirty="1" borderFillIDRef="{bfid}">'
                           f'<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" vertAlign="{va}" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" textHeight="0" hasTextRef="0" hasNumRef="0">{inner}</hp:subList>'
                           f'<hp:cellAddr colAddr="{x["c"]}" rowAddr="{x["r"]}"/><hp:cellSpan colSpan="{x["cs"]}" rowSpan="{x["rs"]}"/>'
                           f'<hp:cellSz width="{w}" height="{h}"/><hp:cellMargin left="{pad[3]}" right="{pad[1]}" top="{pad[0]}" bottom="{pad[2]}"/></hp:tc>')
            trs.append('<hp:tr>' + ''.join(tcs) + '</hp:tr>')
        m = tcss.get('margin', '0').split(); 
        m = (m * 4)[:4] if len(m) in (1, 4) else ([m[0], m[1], m[0], m[1]] if len(m) == 2 else [m[0], m[1], m[2], m[1]])
        auto_l, auto_r = m[3] == 'auto', m[1] == 'auto'
        om = [0 if v == 'auto' else length(v) for v in m]
        inline = tcss.get('display') == 'inline-table'
        halign = 'CENTER' if auto_l and auto_r else 'RIGHT' if auto_l else 'LEFT'
        s.oid += 1; s.z += 1
        none_bf = s.bf((('NONE','0.1 mm','#000000'),)*4 + ('none',))
        return (f'<hp:tbl id="{s.oid}" zOrder="{s.z}" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="CELL" repeatHeader="1" rowCnt="{nrow}" colCnt="{ncol}" cellSpacing="0" borderFillIDRef="{none_bf}" noAdjust="0">'
                f'<hp:sz width="{sum(cols)}" widthRelTo="ABSOLUTE" height="{sum(rowh)}" heightRelTo="ABSOLUTE" protect="0"/>'
                f'<hp:pos treatAsChar="{1 if inline else 0}" affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" horzRelTo="{"PARA" if inline else "COLUMN"}" vertAlign="TOP" horzAlign="{halign}" vertOffset="0" horzOffset="0"/>'
                f'<hp:outMargin left="{om[3]}" right="{om[1]}" top="{om[0]}" bottom="{om[2]}"/><hp:inMargin left="510" right="510" top="141" bottom="141"/>'
                + ''.join(trs) + '</hp:tbl>')

NSDECL = ('xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
    'xmlns:hp10="http://www.hancom.co.kr/hwpml/2016/paragraph" xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core" xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" '
    'xmlns:hhs="http://www.hancom.co.kr/hwpml/2011/history" xmlns:hm="http://www.hancom.co.kr/hwpml/2011/master-page" '
    'xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf" xmlns:dc="http://purl.org/dc/elements/1.1/" '
    'xmlns:opf="http://www.idpf.org/2007/opf/" xmlns:ooxmlchart="http://www.hancom.co.kr/hwpml/2016/ooxmlchart" '
    'xmlns:hwpunitchar="http://www.hancom.co.kr/hwpml/2016/HwpUnitChar" xmlns:epub="http://www.idpf.org/2007/ops" '
    'xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0"')

def page_setup(src):
    """@page size / margin / page counter from the HTML <style>"""
    w, h, mg, pnum, side = 59528, 84188, [5668, 8504, 4252, 8504], False, ''
    m = re.search(r'@page\s*\{', src)
    if m:
        j, depth = m.end(), 1                          # 중괄호를 직접 세어 @page 블록의 끝을 찾는다(안쪽 @bottom-center 가 있든 없든). 정규식은 뒤의 다른 규칙까지 삼켰다
        while j < len(src) and depth: depth += (src[j] == '{') - (src[j] == '}'); j += 1
        body = src[m.end():j - 1]
        css = parse_css(re.sub(r'@[\w-]+\s*\{[^}]*\}', '', body))
        if 'size' in css:
            sz = css['size'].split()
            if len(sz) >= 2 and re.match(r'[\d.]', sz[0]): w, h = length(sz[0]), length(sz[1])
            elif sz[0].upper() == 'A4': w, h = 59528, 84188
        if 'margin' in css:
            v = [length(x) for x in css['margin'].split()]
            mg = (v * 4)[:4] if len(v) in (1, 4) else ([v[0], v[1], v[0], v[1]] if len(v) == 2 else [v[0], v[1], v[2], v[1]])
        pc = re.search(r'@bottom-center\s*\{[^}]*content:([^;}]*)', body)
        if pc and 'counter(page)' in pc.group(1):
            pnum = True; q = re.findall(r'"([^"]*)"', pc.group(1)); side = q[0].strip() if q else ''
    return w, h, mg, pnum, side

def build(src_html, out):
    src = open(src_html, encoding='utf-8').read()
    doc = lxml.html.document_fromstring(src)
    inline_style_rules(doc)
    w, h, (mt, mr, mb, ml), pnum, side = page_setup(src)
    pg_div = doc.xpath('//div[@class="page"]')
    if '@page' not in src and pg_div:        # @page가 없는 화면용 HTML은 .page의 padding을 쪽 여백으로 본다(HTML이 의도한 여백)
        pv = parse_css(pg_div[0].get('style')).get('padding', '').split()
        if pv:
            L = [length(x) for x in pv]
            mt, mr, mb, ml = (L * 4)[:4] if len(L) in (1, 4) else ([L[0], L[1], L[0], L[1]] if len(L) == 2 else [L[0], L[1], L[2], L[1]])
    footer = mb // 2 if pnum else 0
    secpr = (f'<hp:secPr id="" textDirection="HORIZONTAL" spaceColumns="1134" tabStop="8000" tabStopVal="4000" tabStopUnit="HWPUNIT" outlineShapeIDRef="1" memoShapeIDRef="0" textVerticalWidthHead="0" masterPageCnt="0">'
        '<hp:grid lineGrid="0" charGrid="0" wonggojiFormat="0"/><hp:startNum pageStartsOn="BOTH" page="0" pic="0" tbl="0" equation="0"/>'
        '<hp:visibility hideFirstHeader="0" hideFirstFooter="0" hideFirstMasterPage="0" border="SHOW_ALL" fill="SHOW_ALL" hideFirstPageNum="0" hideFirstEmptyLine="0" showLineNumber="0"/>'
        '<hp:lineNumberShape restartType="0" countBy="0" distance="0" startNumber="0"/>'
        f'<hp:pagePr landscape="WIDELY" width="{w}" height="{h}" gutterType="LEFT_ONLY"><hp:margin header="0" footer="{footer}" gutter="0" left="{ml}" right="{mr}" top="{mt}" bottom="{mb - footer}"/></hp:pagePr>'
        '<hp:footNotePr><hp:autoNumFormat type="DIGIT" userChar="" prefixChar="" suffixChar=")" supscript="0"/><hp:noteLine length="-1" type="SOLID" width="0.12 mm" color="#000000"/><hp:noteSpacing betweenNotes="283" belowLine="567" aboveLine="850"/><hp:numbering type="CONTINUOUS" newNum="1"/><hp:placement place="EACH_COLUMN" beneathText="0"/></hp:footNotePr>'
        '<hp:endNotePr><hp:autoNumFormat type="DIGIT" userChar="" prefixChar="" suffixChar=")" supscript="0"/><hp:noteLine length="14692344" type="SOLID" width="0.12 mm" color="#000000"/><hp:noteSpacing betweenNotes="0" belowLine="567" aboveLine="850"/><hp:numbering type="CONTINUOUS" newNum="1"/><hp:placement place="END_OF_DOCUMENT" beneathText="0"/></hp:endNotePr>'
        + ''.join(f'<hp:pageBorderFill type="{t}" borderFillIDRef="1" textBorder="PAPER" headerInside="0" footerInside="0" fillArea="PAPER"><hp:offset left="1417" right="1417" top="1417" bottom="1417"/></hp:pageBorderFill>' for t in ('BOTH','EVEN','ODD'))
        + '</hp:secPr><hp:ctrl><hp:colPr id="" type="NEWSPAPER" layout="LEFT" colCount="1" sameSz="1" sameGap="0"/></hp:ctrl>'
        + (f'<hp:ctrl><hp:pageNum pos="BOTTOM_CENTER" formatType="DIGIT" sideChar="{H.escape(side)}"/></hp:ctrl>' if pnum else ''))
    b = Builder(); b.content_w = w - ml - mr
    body = doc.body
    page = body.find('.//div[@class="page"]')
    root = page if page is not None else body
    inherit = {k: v for k, v in parse_css(body.get('style')).items() if k in CHAR_KEYS and k != 'background-color'}
    paras = b.blocks(root, inherit, secpr)
    section = f'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?><hs:sec {NSDECL}>' + ''.join(paras) + '</hs:sec>'

    # ---------- header ----------
    fonts = ''.join(f'<hh:fontface lang="{l}" fontCnt="{len(b.fonts)}">' + ''.join(
        f'<hh:font id="{i}" face="{H.escape(f)}" type="TTF" isEmbedded="0"><hh:typeInfo familyType="FCAT_GOTHIC" weight="6" proportion="4" contrast="0" strokeVariation="1" armStyle="1" letterform="1" midline="1" xHeight="1"/></hh:font>'
        for i, f in enumerate(b.fonts)) + '</hh:fontface>' for l in LANGS)
    def bfxml(i, key):
        sides = ''.join(f'<hh:{n} type="{t}" width="{wd}" color="{c}"/>' for n, (t, wd, c) in zip(('leftBorder','rightBorder','topBorder','bottomBorder'), key[:4]))
        fill = '' if key[4] is None else f'<hc:fillBrush><hc:winBrush faceColor="{key[4]}" hatchColor="#999999" alpha="0"/></hc:fillBrush>'
        dg = key[5] if len(key) > 5 else ((), '0.1 mm', '#000000')
        sl = 'CENTER' if 'slash' in dg[0] else 'NONE'; bs = 'CENTER' if 'backSlash' in dg[0] else 'NONE'
        return (f'<hh:borderFill id="{i}" threeD="0" shadow="0" centerLine="NONE" breakCellSeparateLine="0"><hh:slash type="{sl}" Crooked="0" isCounter="0"/>'
                f'<hh:backSlash type="{bs}" Crooked="0" isCounter="0"/>{sides}<hh:diagonal type="SOLID" width="{dg[1]}" color="{dg[2]}"/>{fill}</hh:borderFill>')
    a7 = lambda tag, vals: f'<hh:{tag} ' + ' '.join(f'{l.lower()}="{v}"' for l, v in zip(LANGS, vals)) + '/>'
    def cpxml(i, k):
        size, han, lat, col, bold, ital, und, strike, sp, ratio, va, shade = k
        cbf = b.bf((('NONE','0.1 mm','#000000'),)*4 + ('none',))
        return (f'<hh:charPr id="{i}" height="{size}" textColor="{col}" shadeColor="{shade or "none"}" useFontSpace="0" useKerning="0" symMark="NONE" borderFillIDRef="{cbf}">'
                + a7('fontRef', [han, lat, han, han, han, han, han]) + a7('ratio', [ratio]*7) + a7('spacing', [sp]*7)
                + a7('relSz', [100]*7) + a7('offset', [0]*7) + ('<hh:bold/>' if bold else '') + ('<hh:italic/>' if ital else '')
                + f'<hh:underline type="{"BOTTOM" if und else "NONE"}" shape="SOLID" color="{col}"/>'
                + f'<hh:strikeout shape="{"SOLID" if strike else "NONE"}" color="{col}"/><hh:outline type="NONE"/>'
                + '<hh:shadow type="NONE" color="#C0C0C0" offsetX="10" offsetY="10"/>'
                + ('<hh:supscript/>' if va == 'super' else '<hh:subscript/>' if va == 'sub' else '') + '</hh:charPr>')
    def mgxml(k, mult):
        al, left, ind, right, prev, nxt, (lt, lv), _, _ = k
        return (f'<hh:margin><hc:intent value="{ind*mult}" unit="HWPUNIT"/><hc:left value="{left*mult}" unit="HWPUNIT"/><hc:right value="{right*mult}" unit="HWPUNIT"/>'
                f'<hc:prev value="{prev*mult}" unit="HWPUNIT"/><hc:next value="{nxt*mult}" unit="HWPUNIT"/></hh:margin>'
                f'<hh:lineSpacing type="{lt}" value="{lv if lt == "PERCENT" else lv*mult}" unit="HWPUNIT"/>')
    def ppxml(i, k):
        return (f'<hh:paraPr id="{i}" tabPrIDRef="0" condense="0" fontLineHeight="0" snapToGrid="1" suppressLineNumbers="0" checked="0">'
                f'<hh:align horizontal="{k[0]}" vertical="BASELINE"/><hh:heading type="NONE" idRef="0" level="0"/>'
                f'<hh:breakSetting breakLatinWord="KEEP_WORD" breakNonLatinWord="{k[8]}" widowOrphan="0" keepWithNext="0" keepLines="0" pageBreakBefore="0" lineWrap="BREAK"/>'
                '<hh:autoSpacing eAsianEng="0" eAsianNum="0"/>'
                f'<hp:switch><hp:case hp:required-namespace="http://www.hancom.co.kr/hwpml/2016/HwpUnitChar">{mgxml(k,1)}</hp:case><hp:default>{mgxml(k,2)}</hp:default></hp:switch>'
                f'<hh:border borderFillIDRef="{k[7]}" offsetLeft="0" offsetRight="0" offsetTop="0" offsetBottom="0" connect="0" ignoreMargin="0"/></hh:paraPr>')
    chars = ''.join(cpxml(i, k) for i, k in enumerate(b.charPrs))   # may register a borderFill, so build before borderFills
    paras_x = ''.join(ppxml(i, k) for i, k in enumerate(b.paraPrs))
    bfs = ''.join(bfxml(i + 1, k) for i, k in enumerate(b.borderFills))
    fmts = [('DIGIT','^1.'),('HANGUL_SYLLABLE','^2.'),('DIGIT','^3)'),('HANGUL_SYLLABLE','^4)'),('DIGIT','(^5)'),('HANGUL_SYLLABLE','(^6)'),('CIRCLED_DIGIT','^7')]
    numbering = '<hh:numberings itemCnt="1"><hh:numbering id="1" start="0">' + ''.join(
        f'<hh:paraHead start="1" level="{i+1}" align="LEFT" useInstWidth="1" autoIndent="1" widthAdjust="0" textOffsetType="PERCENT" textOffset="50" numFormat="{f}" charPrIDRef="4294967295" checkable="0">{t}</hh:paraHead>'
        for i, (f, t) in enumerate(fmts)) + '</hh:numbering></hh:numberings>'
    header = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?><hh:head {NSDECL} version="1.4" secCnt="1">'
        '<hh:beginNum page="1" footnote="1" endnote="1" pic="1" tbl="1" equation="1"/><hh:refList>'
        f'<hh:fontfaces itemCnt="7">{fonts}</hh:fontfaces><hh:borderFills itemCnt="{len(b.borderFills)}">{bfs}</hh:borderFills>'
        f'<hh:charProperties itemCnt="{len(b.charPrs)}">{chars}</hh:charProperties>'
        '<hh:tabProperties itemCnt="1"><hh:tabPr id="0" autoTabLeft="0" autoTabRight="0"/></hh:tabProperties>'
        f'{numbering}<hh:paraProperties itemCnt="{len(b.paraPrs)}">{paras_x}</hh:paraProperties>'
        '<hh:styles itemCnt="1"><hh:style id="0" type="PARA" name="바탕글" engName="Normal" paraPrIDRef="0" charPrIDRef="0" nextStyleIDRef="0" langID="1042" lockForm="0"/></hh:styles>'
        '</hh:refList><hh:compatibleDocument targetProgram="HWP201X"><hh:layoutCompatibility/></hh:compatibleDocument>'
        '<hh:docOption><hh:linkinfo path="" pageInherit="0" footnoteInherit="0"/></hh:docOption><hh:trackchageConfig flags="56"/></hh:head>')
    title = doc.findtext('.//title') or ''
    imgs = ''.join(f'<opf:item id="image{i}" href="BinData/{n}" media-type="{mt}" isEmbeded="1"/>' for i, (n, _, mt) in enumerate(b.bins, 1))
    hpf = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?><opf:package {NSDECL} version="" unique-identifier="" id="">'
           f'<opf:metadata><opf:title>{H.escape(title)}</opf:title><opf:language>ko</opf:language></opf:metadata>'
           '<opf:manifest><opf:item id="header" href="Contents/header.xml" media-type="application/xml"/><opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>'
           '<opf:item id="settings" href="settings.xml" media-type="application/xml"/>' + imgs + '</opf:manifest>'
           '<opf:spine><opf:itemref idref="header" linear="yes"/><opf:itemref idref="section0" linear="yes"/></opf:spine></opf:package>')
    container = ('<?xml version="1.0" encoding="UTF-8" standalone="yes" ?><ocf:container xmlns:ocf="urn:oasis:names:tc:opendocument:xmlns:container" xmlns:hpf="http://www.hancom.co.kr/schema/2011/hpf">'
                 '<ocf:rootfiles><ocf:rootfile full-path="Contents/content.hpf" media-type="application/hwpml-package+xml"/><ocf:rootfile full-path="Preview/PrvText.txt" media-type="text/plain"/></ocf:rootfiles></ocf:container>')
    version = '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?><hv:HCFVersion xmlns:hv="http://www.hancom.co.kr/hwpml/2011/version" tagetApplication="WORDPROCESSOR" major="5" minor="1" micro="0" buildNumber="1" os="1" xmlVersion="1.4" application="Hancom Office Hangul" appVersion="11, 0, 0, 0"/>'
    settings = '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?><ha:HWPApplicationSetting xmlns:ha="http://www.hancom.co.kr/hwpml/2011/app" xmlns:config="urn:oasis:names:tc:opendocument:xmlns:config:1.0"><ha:CaretPosition listIDRef="0" paraIDRef="0" pos="0"/></ha:HWPApplicationSetting>'
    prv = '\r\n'.join(p.text_content() for p in root if isinstance(p.tag, str))[:1024]
    for x in (section, header, hpf):
        etree.fromstring(x.encode())          # well-formedness check
    with zipfile.ZipFile(out, 'w') as z:
        z.writestr(zipfile.ZipInfo('mimetype'), 'application/hwp+zip', compress_type=zipfile.ZIP_STORED)
        D = zipfile.ZIP_DEFLATED
        z.writestr('version.xml', version, D); z.writestr('Contents/header.xml', header, D); z.writestr('Contents/section0.xml', section, D)
        z.writestr('Preview/PrvText.txt', prv, D); z.writestr('settings.xml', settings, D)
        z.writestr('META-INF/container.xml', container, D)
        z.writestr('META-INF/manifest.xml', '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?><odf:manifest xmlns:odf="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"/>', D)
        z.writestr('Contents/content.hpf', hpf, D)
        for n, data, _ in b.bins: z.writestr('BinData/' + n, data, zipfile.ZIP_STORED if n.endswith(('.jpg', '.png', '.gif')) else D)
    return dict(paragraphs=b.pid, charPr=len(b.charPrs), paraPr=len(b.paraPrs), borderFill=len(b.borderFills), fonts=len(b.fonts), images=len(b.bins))

if __name__ == '__main__':
    print(build(sys.argv[1], sys.argv[2]))

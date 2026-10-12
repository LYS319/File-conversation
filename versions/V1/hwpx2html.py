"""HWPX -> self-contained HTML (formatting expressed as standard inline CSS, units in pt)."""
import sys, zipfile, html, re, base64, io
from lxml import etree
from PIL import Image
from hwp2html import PUA        # 한컴 Wingdings/Symbol 글머리(U+F09F 등) -> 일반 유니코드. 브라우저는 사설 영역 문자를 못 그린다

MAX_BIN_BYTES = 100 * 1024 * 1024
MAX_ZIP_BYTES = 1024 * 1024 * 1024     # 압축을 푼 전체 크기 상한. 정상 HWPX 샘플은 0.5~1.2MB
WEB_IMG_BYTES = 3 * 1024 * 1024        # 이보다 작은 jpeg/png/gif는 원본 그대로 data URI로 넣는다

NS = {'hp':'http://www.hancom.co.kr/hwpml/2011/paragraph','hh':'http://www.hancom.co.kr/hwpml/2011/head',
      'hc':'http://www.hancom.co.kr/hwpml/2011/core','hs':'http://www.hancom.co.kr/hwpml/2011/section'}
HP='{%s}'%NS['hp']; HH='{%s}'%NS['hh']; HC='{%s}'%NS['hc']
pt = lambda u: f'{int(u)/100:g}pt'          # HWPUNIT -> pt (1pt = 100 HWPUNIT)
BORDER = {'SOLID':'solid','DASH':'dashed','DOT':'dotted','DASH_DOT':'dashed','DASH_DOT_DOT':'dashed',
          'LONG_DASH':'dashed','DOUBLE_SLIM':'double','SLIM_THICK':'double','THICK_SLIM':'double',
          'SLIM_THICK_SLIM':'double','CIRCLE':'dotted','WAVE':'solid','DOUBLE_WAVE':'double'}
ALIGN = {'JUSTIFY':'justify','LEFT':'left','RIGHT':'right','CENTER':'center','DISTRIBUTE':'justify','DISTRIBUTE_SPACE':'justify'}
VALIGN = {'TOP':'top','CENTER':'middle','BOTTOM':'bottom'}

def load(path):
    z = zipfile.ZipFile(path)
    if sum(i.file_size for i in z.infolist()) > MAX_ZIP_BYTES: raise ValueError('압축을 푼 크기가 한도(전체 1GB)를 넘음')   # 압축 폭탄 방어
    head = etree.fromstring(z.read('Contents/header.xml'))
    secs = sorted(n for n in z.namelist() if re.match(r'Contents/section\d+\.xml', n))
    return head, [etree.fromstring(z.read(n)) for n in secs]

def is_half(ch):
    o = ord(ch)
    return o < 0x2E80 and not (0x1100 <= o <= 0x11FF) and o not in (0x2007,) or ch in ' \t'

class Conv:
    def __init__(s, head):
        s.fonts = {}
        for ff in head.iter(HH+'fontface'):
            s.fonts[ff.get('lang')] = {f.get('id'): f.get('face') for f in ff.findall(HH+'font')}
        s.bf = {b.get('id'): b for b in head.iter(HH+'borderFill')}
        s.cp = {c.get('id'): c for c in head.iter(HH+'charPr')}
        s.pp = {p.get('id'): p for p in head.iter(HH+'paraPr')}
        s.numbering = {n.get('id'): n for n in head.iter(HH+'numbering')}
        s.numcount = {}
        s.page_css = ''; s.page_num = None

    # ---------- style helpers ----------
    def fill(s, bfid):
        b = s.bf.get(bfid)
        if b is None: return None
        wb = b.find(f'{HC}fillBrush/{HC}winBrush')
        if wb is not None and wb.get('faceColor') not in (None, 'none'):
            return wb.get('faceColor')
        return None
    def borders(s, bfid):
        b = s.bf.get(bfid); out = []
        for side in ('left','right','top','bottom'):
            e = b.find(f'{HH}{side}Border') if b is not None else None
            t = e.get('type') if e is not None else 'NONE'
            if t == 'NONE': out.append(f'border-{side}:none')
            else: out.append(f'border-{side}:{e.get("width").replace(" ","")} {BORDER.get(t,"solid")} {e.get("color")}')
        return out
    def diagonal(s, bfid):
        """cell diagonal (대각선) -> background-image gradient line through the cell corners"""
        b = s.bf.get(bfid)
        if b is None: return None
        dg = b.find(HH+'diagonal'); grads = []
        for tag, direction in (('backSlash', 'to top right'), ('slash', 'to bottom right')):
            e = b.find(HH+tag)
            if e is not None and e.get('type') not in (None, 'NONE'):
                wmm = float(dg.get('width', '0.12 mm').split()[0]); col = dg.get('color', '#000000')
                hw = f'{max(wmm/2, 0.15):g}mm'
                grads.append(f'linear-gradient({direction},transparent calc(50% - {hw}),{col} calc(50% - {hw}),{col} calc(50% + {hw}),transparent calc(50% + {hw}))')
        return 'background-image:' + ','.join(grads) if grads else None

    def char_css(s, cid, half=False):
        c = s.cp[cid]; st = []
        fr = c.find(HH+'fontRef')
        fams = [s.fonts['HANGUL'][fr.get('hangul')]]
        lat = s.fonts['LATIN'][fr.get('latin')]
        if lat != fams[0]: fams.append(lat)
        st.append('font-family:' + ','.join(f"'{f}'" for f in fams))
        st.append(f'font-size:{pt(c.get("height"))}')
        if c.get('textColor','#000000') != '#000000': st.append(f'color:{c.get("textColor")}')
        if c.get('shadeColor','none') not in ('none','#FFFFFF'): st.append(f'background-color:{c.get("shadeColor")}')
        if c.find(HH+'bold') is not None: st.append('font-weight:bold')
        if c.find(HH+'italic') is not None: st.append('font-style:italic')
        deco = []
        u = c.find(HH+'underline')
        if u is not None and u.get('type') not in ('NONE', None): deco.append('underline')
        so = c.find(HH+'strikeout')
        if so is not None and so.get('shape') == 'SOLID': deco.append('line-through')
        if deco: st.append('text-decoration:' + ' '.join(deco))
        sp = int(c.find(HH+'spacing').get('hangul'))
        # HWP 자간 is relative to each glyph's width; half-width glyphs (Latin, digits, spaces) are ~0.5em
        if sp: st.append(f'letter-spacing:{sp/(200 if half else 100):g}em')
        ra = int(c.find(HH+'ratio').get('hangul'))
        if ra != 100: st.append(f'font-stretch:{ra}%')
        if c.find(HH+'supscript') is not None: st.append('vertical-align:super')
        if c.find(HH+'subscript') is not None: st.append('vertical-align:sub')
        return ';'.join(st)
    def para_css(s, pid, p_el, first_cid):
        p = s.pp[pid]; st = []
        st.append('text-align:' + ALIGN.get(p.find(HH+'align').get('horizontal'), 'justify'))
        case = p.find(f'{HP}switch/{HP}case')
        box = case if case is not None else p
        mg = box.find(HH+'margin'); v = lambda n: int(mg.find(HC+n).get('value'))
        left, ind = v('left'), v('intent')
        padl = left - min(ind, 0)       # HWP 내어쓰기: first line at `left`, following lines at left+|intent|
        if padl: st.append(f'padding-left:{pt(padl)}')
        if v('right'): st.append(f'padding-right:{pt(v("right"))}')
        if ind: st.append(f'text-indent:{pt(ind)}')
        if v('prev'): st.append(f'margin-top:{pt(v("prev"))}')
        if v('next'): st.append(f'margin-bottom:{pt(v("next"))}')
        ls = box.find(HH+'lineSpacing')
        t, val = ls.get('type'), int(ls.get('value'))
        if t == 'PERCENT': st.append(f'line-height:{val/100:g}')
        elif t == 'FIXED': st.append(f'line-height:{pt(val)}')
        elif t == 'AT_LEAST': st.append(f'line-height:{pt(val)}')
        b = p.find(HH+'border')
        if b is not None:
            f = s.fill(b.get('borderFillIDRef'))
            if f: st.append(f'background-color:{f}')
        bs = p.find(HH+'breakSetting')
        if bs is not None and bs.get('breakNonLatinWord') == 'BREAK_WORD': st.append('word-break:break-all')
        if p_el.get('pageBreak') == '1': st.append('break-before:page')
        if first_cid is not None:     # default font for empty lines / table-only paragraphs
            c = s.cp[first_cid]
            st.append(f'font-size:{pt(c.get("height"))}')
            st.append('font-family:' + "'" + s.fonts['HANGUL'][c.find(HH+'fontRef').get('hangul')] + "'")
        return ';'.join(st)
    def number_prefix(s, pid):
        h = s.pp[pid].find(HH+'heading')
        if h is None or h.get('type') != 'NUMBER': return ''
        lvl = int(h.get('level')) + 1
        num = s.numbering.get(h.get('idRef'))
        key = (h.get('idRef'), lvl); s.numcount[key] = s.numcount.get(key, 0) + 1
        for k in list(s.numcount):
            if k[0] == key[0] and k[1] > lvl: s.numcount[k] = 0
        fmt = '^%d.' % lvl
        if num is not None:
            for ph in num.findall(HH+'paraHead'):
                if ph.get('level') == str(lvl): fmt = ph.text or fmt
        return fmt.replace('^%d' % lvl, str(s.numcount[key])) + ' '

    def picture(s, pic):
        """hp:pic -> <img data URI>. BMP·큰 파일은 웹용 JPEG(최대 1600px)로 줄인다. 크기는 curSz를 pt로 그대로 둔다(html2hwpx가 되읽음)."""
        ref = pic.find(HC + 'img')
        href = s.bin_href.get(ref.get('binaryItemIDRef')) if ref is not None else None
        if not href or href not in s.z.namelist() or s.z.getinfo(href).file_size > MAX_BIN_BYTES: return ''
        data = s.z.read(href)
        im = Image.open(io.BytesIO(data)); fmt = (im.format or '').lower()
        if fmt in ('jpeg', 'png', 'gif') and len(data) <= WEB_IMG_BYTES: mime = fmt
        else:
            if im.mode in ('RGBA', 'LA', 'P'):      # 투명 배경은 흰색으로
                im = im.convert('RGBA'); bg = Image.new('RGB', im.size, 'white'); bg.paste(im, mask=im.split()[3]); im = bg
            im = im.convert('RGB'); im.thumbnail((1600, 1600))
            buf = io.BytesIO(); im.save(buf, 'JPEG', quality=85, optimize=True); data, mime = buf.getvalue(), 'jpeg'
        sz = pic.find(HP + 'curSz')
        alt = html.escape(((pic.findtext(HP + 'shapeComment') or '').strip().splitlines() or [''])[0], quote=True)
        return (f'<img src="data:image/{mime};base64,{base64.b64encode(data).decode()}" alt="{alt}" '
                f'style="width:{pt(sz.get("width"))};height:{pt(sz.get("height"))}">')

    # ---------- content ----------
    def text_of(s, t):
        out = [html.escape(t.text or '', quote=False).translate(PUA)]
        for ch in t:
            tag = etree.QName(ch).localname
            if tag == 'lineBreak': out.append('<br>')
            elif tag == 'fwSpace': out.append('\u2007')
            elif tag == 'nbSpace': out.append('\u00a0')
            elif tag == 'tab': out.append('\t')
            elif tag == 'hyphen': out.append('-')
            out.append(html.escape(ch.tail or '', quote=False).translate(PUA))
        return ''.join(out)

    def paragraph(s, p):
        runs = p.findall(HP+'run')
        first_cid = runs[0].get('charPrIDRef') if runs else None
        parts = []; has_table = False
        prefix = s.number_prefix(p.get('paraPrIDRef'))
        if prefix and first_cid: parts.append(f'<span style="{s.char_css(first_cid)}">{prefix}</span>')
        for r in runs:
            cid = r.get('charPrIDRef'); buf = ''
            def flush():
                nonlocal buf
                if not buf: return
                if int(s.cp[cid].find(HH+'spacing').get('hangul')) == 0:
                    parts.append(f'<span style="{s.char_css(cid)}">{buf}</span>')
                else:   # split into full-width / half-width pieces so CSS spacing matches HWP's proportional 자간
                    for chunk in re.findall(r'(?:<br>|(?:(?!<br>)[^&\s\x21-\x7e\u00a0-\u024f\u2007])|&\w+;)+|(?:&\w+;|<br>|[\s\x21-\x7e\u00a0-\u024f\u2007])+', buf):
                        plain = html.unescape(chunk.replace('<br>', ''))
                        half = bool(plain) and all(is_half(ch) for ch in plain)
                        parts.append(f'<span style="{s.char_css(cid, half)}">{chunk}</span>')
                buf = ''
            for ch in r:
                tag = etree.QName(ch).localname
                if tag == 't': buf += s.text_of(ch)
                elif tag == 'tbl': flush(); parts.append(s.table(ch)); has_table = True
                elif tag == 'pic': flush(); parts.append(s.picture(ch))
                elif tag == 'secPr': s.section(ch)
                elif tag == 'ctrl':
                    pn = ch.find(HP+'pageNum')
                    if pn is not None: s.page_num = pn
            flush()
        style = s.para_css(p.get('paraPrIDRef'), p, first_cid)
        body = ''.join(parts)
        if has_table: return f'<div style="{style}">{body}</div>'
        return f'<p style="{style}">{body or "<br>"}</p>'

    def section(s, sec):
        pg = sec.find(HP+'pagePr'); m = pg.find(HP+'margin'); g = lambda k: int(m.get(k))
        w, h = int(pg.get('width')), int(pg.get('height'))
        if pg.get('landscape') == 'NARROWLY': w, h = h, w
        s.page = dict(w=w, h=h, top=g('top')+g('header'), bottom=g('bottom')+g('footer'), left=g('left')+g('gutter'), right=g('right'))

    def table(s, tbl):
        sz = tbl.find(HP+'sz'); pos = tbl.find(HP+'pos'); om = tbl.find(HP+'outMargin'); im = tbl.find(HP+'inMargin')
        ncol = int(tbl.get('colCnt'))
        cells = []
        for tr in tbl.findall(HP+'tr'):
            for tc in tr.findall(HP+'tc'):
                a = tc.find(HP+'cellAddr'); sp = tc.find(HP+'cellSpan'); csz = tc.find(HP+'cellSz')
                cells.append(dict(tc=tc, r=int(a.get('rowAddr')), c=int(a.get('colAddr')), cs=int(sp.get('colSpan')),
                                  rs=int(sp.get('rowSpan')), w=int(csz.get('width')), h=int(csz.get('height'))))
        # column boundaries from cell addresses and widths
        x = {0: 0}; changed = True
        while changed:
            changed = False
            for c in cells:
                a, b = c['c'], c['c'] + c['cs']
                if a in x and b not in x: x[b] = x[a] + c['w']; changed = True
                elif b in x and a not in x: x[a] = x[b] - c['w']; changed = True
        for i in range(ncol + 1):
            if i not in x: x[i] = x[i-1] if i else 0
        colw = [max(x[i+1] - x[i], 0) for i in range(ncol)]
        # cellzone overrides
        zones = [(int(z.get('startRowAddr')), int(z.get('startColAddr')), int(z.get('endRowAddr')), int(z.get('endColAddr')), z.get('borderFillIDRef'))
                 for z in tbl.iter(HP+'cellzone')]
        st = ['border-collapse:collapse', 'table-layout:fixed', f'width:{pt(sum(colw))}']
        st.append(f'margin:{pt(om.get("top"))} {pt(om.get("right"))} {pt(om.get("bottom"))} {pt(om.get("left"))}')
        if pos.get('treatAsChar') == '1': st += ['display:inline-table', 'vertical-align:top']
        else:
            ha = pos.get('horzAlign')
            if ha == 'CENTER': st[-1] = f'margin:{pt(om.get("top"))} auto {pt(om.get("bottom"))} auto'
            elif ha == 'RIGHT': st[-1] = f'margin:{pt(om.get("top"))} {pt(om.get("right"))} {pt(om.get("bottom"))} auto'
        out = [f'<table style="{";".join(st)}"><colgroup>' + ''.join(f'<col style="width:{pt(w)}">' for w in colw) + '</colgroup>']
        rows = {}
        for c in cells: rows.setdefault(c['r'], []).append(c)
        for r in sorted(rows):
            out.append('<tr>')
            for c in sorted(rows[r], key=lambda c: c['c']):
                tc = c['tc']; sub = tc.find(HP+'subList')
                bfid = tc.get('borderFillIDRef')
                mg = tc.find(HP+'cellMargin') if tc.get('hasMargin') == '1' else im
                cst = [f'width:{pt(c["w"])}', f'height:{pt(c["h"])}',
                       f'padding:{pt(mg.get("top"))} {pt(mg.get("right"))} {pt(mg.get("bottom"))} {pt(mg.get("left"))}',
                       'vertical-align:' + VALIGN.get(sub.get('vertAlign'), 'top')] + s.borders(bfid)
                f = s.fill(bfid)
                if f: cst.append(f'background-color:{f}')
                d = s.diagonal(bfid)
                if d: cst.append(d)
                span = (f' colspan="{c["cs"]}"' if c['cs'] > 1 else '') + (f' rowspan="{c["rs"]}"' if c['rs'] > 1 else '')
                inner = ''.join(s.paragraph(p) for p in sub.findall(HP+'p'))
                out.append(f'<td{span} style="{";".join(cst)}">{inner}</td>')
            out.append('</tr>')
        out.append('</table>')
        return ''.join(out)

def convert(src, dst):
    head, secs = load(src)
    cv = Conv(head); blocks = []
    cv.z = zipfile.ZipFile(src)
    cv.bin_href = {i.get('id'): i.get('href') for i in etree.fromstring(cv.z.read('Contents/content.hpf')).iter('{http://www.idpf.org/2007/opf/}item')
                   if (i.get('href') or '').startswith('BinData/')}
    for sec in secs:
        for p in sec.findall(HP+'p'):
            blocks.append(cv.paragraph(p))
    pg = cv.page
    title = re.sub(r'<[^>]+>', '', blocks[0]) if blocks else 'document'
    pagenum = ''
    if cv.page_num is not None:
        sc = cv.page_num.get('sideChar', '')
        pagenum = f' @bottom-center{{content:"{sc} " counter(page) " {sc}";}}' if sc else ' @bottom-center{content:counter(page);}'
    css = (f'@page{{size:{pt(pg["w"])} {pt(pg["h"])};margin:{pt(pg["top"])} {pt(pg["right"])} {pt(pg["bottom"])} {pt(pg["left"])};{pagenum}}}\n'
           'body{margin:0;background:#e9eaec;color:#000}\n'
           f'.page{{box-sizing:border-box;width:{pt(pg["w"])};min-height:{pt(pg["h"])};margin:24px auto;background:#fff;'
           f'padding:{pt(pg["top"])} {pt(pg["right"])} {pt(pg["bottom"])} {pt(pg["left"])};box-shadow:0 2px 10px rgba(0,0,0,.15)}}\n'
           'p,div{margin:0}\np,div,td{white-space:pre-wrap;word-break:keep-all;overflow-wrap:break-word}\ntd>p,td>div{white-space:pre-wrap}\n'
           '@media print{body{background:#fff}.page{box-shadow:none;margin:0;padding:0;width:auto;min-height:0}}')
    doc = (f'<!DOCTYPE html>\n<html lang="ko"><head><meta charset="utf-8">\n<title>{html.escape(title.strip())}</title>\n'
           f'<style>\n{css}\n</style></head>\n<body><div class="page">\n' + '\n'.join(blocks) + '\n</div></body></html>\n')
    open(dst, 'w', encoding='utf-8').write(doc)
    return len(blocks)

if __name__ == '__main__':
    print(convert(sys.argv[1], sys.argv[2]), 'top-level paragraphs')

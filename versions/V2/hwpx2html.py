"""HWPX -> self-contained HTML (formatting expressed as standard inline CSS, units in pt)."""
import os, sys, zipfile, html, re, base64, io
from lxml import etree
from PIL import Image
from hwp2html import PUA, HANGUL_DELTA, SPLIT_ON, split_plan, head_rows, spacing_css, keep_rows      # 한컴 Wingdings/Symbol 글머리(U+F09F 등) -> 일반 유니코드. 브라우저는 사설 영역 문자를 못 그린다

_SL = os.environ.get('STORED_LAYOUT', '')
STORED = _SL in ('1', 'all', 'lines')       # 저장된 줄 끊김대로
STORED_P = _SL in ('1', 'all', 'pages')     # 저장된 쪽 시작대로      # 실험: 한컴이 저장한 줄 끊김·쪽 시작(linesegarray)을 그대로 따른다
MK = chr(1)         # 저장된 줄 시작 자리 표식(글 안)
LB = '<!--LB-->'    # 줄 사이 표식(부품 목록 안)
SKIPPED = []        # 읽지 못해 뺀 그림의 오류 이름(변환 끝에 경고로 알린다)
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
    pend = None         # 보류 중인 떠 있는 표(최상위 문단의 voff 가 있는 자리 차지 표)

    def emit_pending(s):
        """보류한 떠 있는 표를 HTML 로: 표마다 (앵커 위치 + voff) 에서 지금까지 놓은 내용의 끝을 뺀 만큼을 위쪽 간격으로 준다."""
        pd, s.pend = s.pend, None; out = ''; end = pd['end']
        for html_, voff, fh in pd['floats']:
            top = pd['vp'] + int(voff * 100); m = max(0, top - end) / 100
            tag_end = html_.index('>'); tag = html_[:tag_end]; k = tag.rindex('"', 0, tag.index(' data-voff="'))
            out += re.sub(r' data-(?:voff|fh)="[\d.]+"', '', tag[:k] + f';margin-top:{m:g}pt' + tag[k:]) + html_[tag_end:]
            end = max(end, top) + int(fh * 100)
        return out

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
        s.hf = {'header': [], 'footer': []}          # 머리글·바닥글 본문(HTML). 쪽마다 반복은 못 하고 본문 맨 앞/끝에 한 번만 넣는다

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
                wmm = float(dg.get('width', '0.12 mm').split()[0]) if dg is not None else 0.12      # 대각선 굵기 정보(diagonal)가 없는 테두리도 있다
                col = dg.get('color', '#000000') if dg is not None else '#000000'
                hw = f'{max(wmm/2, 0.15):g}mm'
                grads.append(f'linear-gradient({direction},transparent calc(50% - {hw}),{col} calc(50% - {hw}),{col} calc(50% + {hw}),transparent calc(50% + {hw}))')
        return 'background-image:' + ','.join(grads) if grads else None

    def char_css(s, cid, half=False):
        c = s.cp[cid]; st = []
        fr = c.find(HH+'fontRef')
        fams = []       # 글꼴 목록(fontfaces)에 한글·영어 칸이 없는 파일도 있다(KeyError 'LATIN')
        for lang, key in (('HANGUL', 'hangul'), ('LATIN', 'latin')):
            f = s.fonts.get(lang, {}).get(fr.get(key)) if fr is not None else None
            if f and f not in fams: fams.append(f)
        if fams: st.append('font-family:' + ','.join(f"'{f}'" for f in fams))
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
        ra = int(c.find(HH+'ratio').get('hangul'))
        # 장평(가로 비율)은 CSS font-stretch 로는 안 줄어든다(나눔 글꼴은 폭 변형이 없다) -> HWP 경로(hwp2html.span_style)처럼 글자 간격에 합친다: (자간 + 장평 - 100)%.
        # 장평 70% 제목이 한컴은 한 줄인데 우리는 글자가 줄지 않아 두 줄이 됐다(issue2004_cell_image_stack).
        st += spacing_css((sp + ra - 100) / (200 if half else 100), 0 if half else HANGUL_DELTA.get(fams[0] if fams else '', 0) * ra / 100)      # 한컴 글꼴 대 나눔 글꼴의 한글 폭 차이 보정(hwp2html.HANGUL_DELTA)은 PDF 에서만 더한다
        if c.find(HH+'supscript') is not None: st.append('vertical-align:super')
        if c.find(HH+'subscript') is not None: st.append('vertical-align:sub')
        return ';'.join(st)
    def para_css(s, pid, p_el, first_cid, trim=()):
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
        ls = box.find(HH+'lineSpacing')
        t, val = ls.get('type'), int(ls.get('value'))
        mt, mb = v('prev') / 100, v('next') / 100
        if trim and t == 'PERCENT' and val > 100 and first_cid is not None:
            # 한컴은 줄 간격(%)을 줄 아래에만 붙이고 칸·쪽의 맨 위 줄 앞/맨 아래 줄 뒤에는 안 붙인다(12pt 글자 한 줄 칸 = 12pt + 여백).
            # CSS line-height 는 줄 위아래로 반씩 붙어 같은 칸이 더 커진다 -> 칸 안 첫/끝 문단은 반씩 되돌려 한컴과 같은 높이·글 위치로 만든다.
            half = (val / 100 - 1) / 2 * int(s.cp[first_cid].get('height')) / 100
            if 'top' in trim: mt -= half
            if 'bottom' in trim: mb -= half
        if mt: st.append(f'margin-top:{mt:.2f}pt')
        if mb: st.append(f'margin-bottom:{mb:.2f}pt')
        if t == 'PERCENT': st.append(f'line-height:{val/100:g}')
        elif t == 'FIXED': st.append(f'line-height:{pt(val)}')
        elif t == 'AT_LEAST': st.append(f'line-height:{pt(val)}')
        b = p.find(HH+'border')
        if b is not None:
            f = s.fill(b.get('borderFillIDRef'))
            if f: st.append(f'background-color:{f}')
        bs = p.find(HH+'breakSetting')
        if bs is not None and bs.get('breakNonLatinWord') == 'BREAK_WORD': st.append('word-break:break-all')
        if bs is not None and bs.get('widowOrphan') == '1': st.append('orphans:2;widows:2')
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
        try:        # 읽을 수 없는 그림(SVG·WMF·EMF·깨진 파일) 한 장 때문에 문서 전체 변환이 실패하지 않게 뺀다
            im = Image.open(io.BytesIO(data)); fmt = (im.format or '').lower()
            if fmt in ('jpeg', 'png', 'gif') and len(data) <= WEB_IMG_BYTES: mime = fmt
            else:
                if im.mode in ('RGBA', 'LA', 'P'):      # 투명 배경은 흰색으로
                    im = im.convert('RGBA'); bg = Image.new('RGB', im.size, 'white'); bg.paste(im, mask=im.split()[3]); im = bg
                im = im.convert('RGB'); im.thumbnail((1600, 1600))
                buf = io.BytesIO(); im.save(buf, 'JPEG', quality=85, optimize=True); data, mime = buf.getvalue(), 'jpeg'
        except Exception as e:
            SKIPPED.append(type(e).__name__); return ''
        sz = pic.find(HP + 'curSz')
        alt = html.escape(((pic.findtext(HP + 'shapeComment') or '').strip().splitlines() or [''])[0], quote=True)
        return (f'<img src="data:image/{mime};base64,{base64.b64encode(data).decode()}" alt="{alt}" '
                f'style="width:{pt(sz.get("width"))};height:{pt(sz.get("height"))}">')

    # ---------- content ----------
    def text_of(s, t, brk=None):
        out = []

        def put(txt):
            if not brk: out.append(html.escape(txt, quote=False).translate(PUA)); return
            for c in txt:        # \uc800\uc7a5\ub41c \uc904 \uc2dc\uc791 \uc704\uce58(textpos)\ub294 \ubb38\ub2e8 \uae00\uc790 \uc218(\uc81c\uc5b4 \uc694\uc18c 1\uce78\uc529)\ub85c \uc13c \uac12 \u2014 \uadf8 \uc790\ub9ac\uc5d0 \ud45c\uc2dd MK \ub97c \ub454\ub2e4
                if brk['pos'] in brk['set']: out.append(MK)
                out.append(html.escape(c, quote=False).translate(PUA)); brk['pos'] += 1
        put(t.text or '')
        for ch in t:
            tag = etree.QName(ch).localname
            if tag == 'lineBreak': out.append('<br>')
            elif tag == 'fwSpace': out.append('\u2007')
            elif tag == 'nbSpace': out.append('\u00a0')
            elif tag == 'tab': out.append('\t')
            elif tag == 'hyphen': out.append('-')
            if brk and tag in ('lineBreak', 'fwSpace', 'nbSpace', 'tab', 'hyphen'): brk['pos'] += 1
            put(ch.tail or '')
        return ''.join(out)

    def paragraph(s, p, trim=(), top=False):
        runs = p.findall(HP+'run')
        first_cid = runs[0].get('charPrIDRef') if runs else None
        parts = []; has_table = False
        brk = single = None
        if STORED:
            sg0 = p.find(HP+'linesegarray')
            if sg0 is not None and len(sg0) and all(int(l.get('vertsize') or 0) > 0 for l in sg0) and not any(True for _ in p.iter(HP+'tbl', HP+'pic', HP+'rect', HP+'lineBreak', HP+'tab')):
                if len(sg0) == 1: single = True
                else: brk = {'pos': 0, 'set': {int(l.get('textpos')) for l in sg0[1:]}}
        prefix = s.number_prefix(p.get('paraPrIDRef'))
        if prefix and first_cid: parts.append(f'<span style="{s.char_css(first_cid)}">{prefix}</span>')
        for r in runs:
            cid = r.get('charPrIDRef'); buf = ''
            def flush():
                nonlocal buf
                if not buf: return
                if MK in buf:
                    segs, buf = buf.split(MK), ''
                    for si, sg_ in enumerate(segs):
                        if si: parts.append(LB)
                        if sg_: buf = sg_; flush1()
                    buf = ''; return
                flush1()

            def flush1():
                nonlocal buf
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
                if tag == 't': buf += s.text_of(ch, brk)
                elif tag == 'tbl': flush(); parts.append(s.table(ch)); has_table = True
                elif tag == 'pic': flush(); parts.append(s.picture(ch))
                elif tag == 'secPr': s.section(ch)
                elif tag == 'ctrl':
                    pn = ch.find(HP+'pageNum')
                    if pn is not None: s.page_num = pn
                    for kind in ('header', 'footer'):
                        hf = ch.find(HP+kind)
                        sub = hf.find(HP+'subList') if hf is not None else None
                        if sub is not None:
                            h = ''.join(s.paragraph(q) for q in sub.findall(HP+'p'))
                            if h and h not in s.hf[kind]: s.hf[kind].append(h)       # 홀·짝 쪽이 서로 다르면 둘 다, 같으면 한 번만
                elif tag in ('checkBtn', 'radioBtn', 'btn'):    # 서식의 양식 컨트롤: 모양은 못 그리고 기호 + 설명 글만 남긴다
                    mark = {'checkBtn': ('☐', '☑'), 'radioBtn': ('○', '◉')}.get(tag)
                    buf += html.escape((mark[ch.get('value') == 'CHECKED'] + ' ' if mark else '') + (ch.get('caption') or ''), quote=False)
                elif tag == 'rect':                              # 글상자: 안의 글만 가져온다(도형 모양·테두리는 무시)
                    dt = ch.find(HP+'drawText'); sub = dt.find(HP+'subList') if dt is not None else None
                    if sub is not None:
                        flush(); has_table = True                # <p> 안에 <div> 를 넣을 수 없어 바깥도 <div> 로
                        parts.append('<div style="display:inline-block;vertical-align:top">' + ''.join(s.paragraph(q) for q in sub.findall(HP+'p')) + '</div>')
            flush()
        fl = [i for i, x in enumerate(parts) if x.startswith('<table') and ' data-voff="' in x[:x.index('>')]]
        if fl:
            # 문단 위에서 voff 만큼 아래에 떠 있는 표(자리 차지): 문단의 줄 안 내용(글·글자처럼 취급 표)은 문단 맨 위에 놓이고 떠 있는 표는 그 아래 voff 지점에 온다.
            # XML 순서(떠 있는 표가 먼저)대로 쌓으면 결재 표가 본문 표 밑으로 내려갔다(야간방호일지: 쪽이 2장). 줄 안 내용이 있으면 앞에 두고 표에는 (voff - 줄 안 내용 높이)를 위쪽 간격으로 준다.
            others = [x for i, x in enumerate(parts) if i not in fl]
            sg = p.find(HP+'linesegarray'); first = sg[0] if top and sg is not None and len(sg) and int(sg[0].get('vertsize') or 0) > 0 else None       # 저장된 줄 위치가 0/0 인 낡은 파일은 쓰지 않는다
            if first is not None:
                # 최상위 문단: 떠 있는 표를 보류해 두고, 뒤따르는 문단 중 표 위의 빈 틈에 들어가는 것(저장된 줄 위치로 판단)을 먼저 놓은 뒤 표를 놓는다 — convert() 가 처리.
                # 한컴은 자리 차지 표 위쪽 틈에 다음 문단을 넣는다(야간방호일지: 문서번호 상자가 결재 표와 본문 표 사이 y=199 에 있다)
                vp, vs = int(first.get('vertpos')), int(first.get('vertsize'))
                fts = [(parts[i], float(re.search(r' data-voff="([\d.]+)"', parts[i]).group(1)), float(re.search(r' data-fh="([\d.]+)"', parts[i]).group(1))) for i in fl]
                if s.pend: s.pend['floats'] += fts; s.pend['top'] = min(s.pend['top'], vp + int(min(v for _, v, _ in fts) * 100))
                else: s.pend = dict(vp=vp, end=vp + vs, top=vp + int(min(v for _, v, _ in fts) * 100), floats=fts)
                parts = others
            elif any('<img' in x or re.sub(r'<[^>]+>|&nbsp;|\s', '', x) for x in others):
                hs = [float(m.group(1)) for x in others for m in [re.match(r'<table[^>]* data-h="([\d.]+)"', x)] if m]
                line_h = hs and max(hs) or (int(s.cp[first_cid].get('height')) / 100 * 1.6 if first_cid else 0)
                fts = []
                for i in fl:
                    vo = float(re.search(r' data-voff="([\d.]+)"', parts[i]).group(1)); tag_end = parts[i].index('>'); tag = parts[i][:tag_end]
                    k = tag.rindex('"', 0, tag.index(' data-voff="'))        # style="…" 의 닫는 따옴표 앞에 붙여 표 자신의 margin 단축 속성보다 뒤에 오게 한다
                    fts.append(tag[:k] + f';margin-top:{max(0.0, vo - line_h):g}pt' + tag[k:] + parts[i][tag_end:])
                parts = others + fts
            else:
                parts = [x.replace(' data-voff="', ' data-vo="') if i in fl else x for i, x in enumerate(parts)]
        style = s.para_css(p.get('paraPrIDRef'), p, first_cid, () if has_table else trim)
        if (brk or single) and not has_table and parts:
            just = 'text-align-last:justify;' if 'text-align:justify' in style else ''
            if single: parts = ['<span style="display:block;white-space:pre">' + ''.join(parts) + '</span>']
            else:
                lines = [[]]
                for x in parts:
                    if x == LB: lines.append([])
                    else: lines[-1].append(x)
                parts = ['<span style="display:block;white-space:pre;%s">%s</span>' % ('' if k == len(lines) - 1 else just, ''.join(l) or '&nbsp;') for k, l in enumerate(lines)]
        if has_table and all(x.startswith('<table') or not ('<img' in x or re.sub(r'<[^>]+>|\s', '', x)) for x in parts):
            # 표만 들어 있는 문단: 한 줄 안의 통째 상자(inline-table)로 두면 쪽 경계에서 표가 쪼개지지 않아 한 쪽 가득 비고 다음 쪽으로 넘어간다. 보통 표(block)로 바꾼다.
            al = re.search(r'text-align:(\w+)', style)
            def _blockify(x):
                tag, rest = x[:x.index('>')].replace(';display:inline-table;vertical-align:top', ''), x[x.index('>'):]
                # 글자처럼 취급 표는 문단 정렬을 따른다(가운데·오른쪽 정렬 문단의 표; 오른쪽이면 오른쪽 바깥 여백만큼 안쪽 — 공고문 한컴 PDF 와 대조해 표 x 78.4pt 일치)
                k = tag.index('"', tag.index('style="') + 7)       # style 속성의 닫는 따옴표(뒤에 data-* 표식이 올 수 있다)
                if al and al.group(1) == 'center': tag = tag[:k] + ';margin-left:auto;margin-right:auto' + tag[k:]
                elif al and al.group(1) == 'right': tag = tag[:k] + ';margin-left:auto' + tag[k:]
                return tag + rest
            parts = [_blockify(x) if x.startswith('<table') else x for x in parts if x.startswith('<table') or '<img' in x or re.sub(r'<[^>]+>|\s', '', x)]      # 표 앞뒤의 공백뿐인 글은 뺀다(둘째 줄로 넘어가 빈 줄을 만들어 아래 표를 한 줄 밀었다)
            # 표는 그 문단의 첫 줄에 놓이니 시작 위치 = 왼쪽 여백 + (들여쓰기일 때만) 들여쓰기. 내어쓰기(음수)의 padding-left 는 둘째 줄부터의 위치라 표에는 맞지 않는다
            # (공고문: 내어쓰기 38pt 문단의 표가 한컴보다 오른쪽 37pt 에 놓였다 — 한컴 PDF 세로선 x=63.9 대 우리 100.7)
            mp, mi = re.search(r'padding-left:(-?[\d.]+)pt', style), re.search(r'text-indent:(-?[\d.]+)pt', style)
            if mp or mi:
                pl, ti = float(mp.group(1)) if mp else 0.0, float(mi.group(1)) if mi else 0.0
                style = re.sub(r'padding-left:-?[\d.]+pt;?|text-indent:-?[\d.]+pt;?', '', style)
                x = pl + ti        # 내어쓰기: pl = 왼쪽 − 들여쓰기 이므로 pl + 들여쓰기 = 왼쪽, 들여쓰기(양수): pl = 왼쪽 이므로 왼쪽 + 들여쓰기
                if x > 0: style += f';padding-left:{x:.2f}pt'
        body = ''.join(parts)
        if has_table: return f'<div style="{style}">{body}</div>'
        return f'<p style="{style}">{body or "<br>"}</p>'

    def section(s, sec):
        pg = sec.find(HP+'pagePr'); m = pg.find(HP+'margin'); g = lambda k: int(m.get(k))
        w, h = int(pg.get('width')), int(pg.get('height'))
        if pg.get('landscape') == 'NARROWLY': w, h = h, w
        s.page = dict(w=w, h=h, top=g('top')+g('header'), bottom=g('bottom')+g('footer'), left=g('left')+g('gutter'), right=g('right'))

    def free_text(s, sub, h):
        """200pt 넘는 큰 칸에 글이 가득한 경우(서술란: 높이 1pt 당 1자 이상). 한컴은 이런 칸을 쪽 경계에서 줄 단위로 나눠 잇는데, 칸 높이(height)를
        그대로 지정하면 WeasyPrint 가 나뉜 앞부분도 그 높이로 쳐서 칸 전체를 다음 쪽으로 밀어 버린다(쪽이 한 장씩 더 생기는 원인).
        글이 가득한 칸은 높이를 글이 정하니 height 를 빼도 같다. 글이 적은 빈 답안 칸은 해당 안 됨(높이 유지).
        (한컴이 저장한 줄 정보 linesegarray 로 글 높이를 재는 방법은 낡은 값이 들어 있는 파일이 있어 쓰지 않는다.)"""
        return h >= 20000 and len(''.join(sub.itertext()).strip()) >= h / 100

    @staticmethod
    def text_bottom(sub):
        """칸 안 문단들의 저장된 줄 정보(linesegarray)로 잰 글 높이 pt = 마지막 줄의 vertpos + vertsize. 줄 정보가 없으면 0(hwp2html.text_bottom 과 같은 뜻)."""
        bot = 0
        for p in sub.findall(HP+'p'):
            sg = p.find(HP+'linesegarray')
            if sg is not None and len(sg): bot = max(bot, (int(sg[-1].get('vertpos')) + int(sg[-1].get('vertsize'))) / 100)
        return bot

    def table(s, tbl):
        sz = tbl.find(HP+'sz'); pos = tbl.find(HP+'pos'); om = tbl.find(HP+'outMargin'); im = tbl.find(HP+'inMargin')
        ncol = int(tbl.get('colCnt'))
        cells = []
        for tr in tbl.findall(HP+'tr'):
            for tc in tr.findall(HP+'tc'):
                a = tc.find(HP+'cellAddr'); sp = tc.find(HP+'cellSpan'); csz = tc.find(HP+'cellSz')
                cells.append(dict(tc=tc, r=int(a.get('rowAddr')), c=int(a.get('colAddr')), cs=int(sp.get('colSpan')),
                                  rs=int(sp.get('rowSpan')), w=int(csz.get('width')), h=int(csz.get('height')), hd=int(tc.get('header') == '1')))
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
        mark = ''
        if pos.get('treatAsChar') == '1':
            st += ['display:inline-table', 'vertical-align:top']
            mark = f' data-h="{(int(sz.get("height")) + int(om.get("top")) + int(om.get("bottom"))) / 100:.2f}"'       # 문단 첫 줄의 높이 어림(같은 문단에 뜬 표의 세로 오프셋을 줄 때)
        else:
            ha = pos.get('horzAlign')
            if ha == 'CENTER': st[-1] = f'margin:{pt(om.get("top"))} auto {pt(om.get("bottom"))} auto'
            elif ha == 'RIGHT': st[-1] = f'margin:{pt(om.get("top"))} {pt(om.get("right"))} {pt(om.get("bottom"))} auto'
            else:
                # 왼쪽 정렬로 떠 있는 표: 문단·단 기준 가로 오프셋만큼 오른쪽(rhwp 렌더 트리와 대조한 HWP 경로와 같은 규칙), 세로 오프셋은 문단 쪽에서 정한다
                ho = int(pos.get('horzOffset') or 0); ho -= (1 << 32) if ho >= (1 << 31) else 0        # 부호 없는 32비트로 적힌 음수(4294967082 = -214) — 그대로 쓰면 표가 4억pt 밖으로 밀려 글이 사라졌다
                if ho > 0 and pos.get('horzRelTo') in ('PARA', 'COLUMN'): st.append(f'margin-left:{pt(int(om.get("left")) + ho)}')
            vo = int(pos.get('vertOffset') or 0); vo -= (1 << 32) if vo >= (1 << 31) else 0
            if vo > 0 and pos.get('vertRelTo') == 'PARA' and tbl.get('textWrap') == 'TOP_AND_BOTTOM':
                mark = f' data-voff="{vo / 100:.2f}" data-fh="{(int(sz.get("height")) + int(om.get("top")) + int(om.get("bottom"))) / 100:.2f}"'
        out = [f'<table style="{";".join(st)}"{mark}><colgroup>' + ''.join(f'<col style="width:{pt(w)}">' for w in colw) + '</colgroup>']
        rows = {}
        for c in cells: rows.setdefault(c['r'], []).append(c)
        cellsplit = STORED and SPLIT_ON and tbl.get('pageBreak') == 'CELL'        # 셀 단위로 나뉘는 표만(HWP 는 표 속성 비트 0~1 = 2)
        nh = head_rows(len(rows), [dict(row=c['r'], rs=c['rs'], hd=c['hd']) for c in cells], tbl.get('repeatHeader') == '1')
        keep = keep_rows(((c['r'], c['rs'], c['h'] / 100) for c in cells), min(rows), max(c['h'] for c in cells if c['r'] == min(rows)) / 100)
        if nh: out.append('<thead>')
        for r in sorted(rows):
            if nh and r == nh: out.append('</thead><tbody>')
            out.append('<tr style="break-after:avoid">' if r in keep else '<tr>')
            rc = sorted(rows[r], key=lambda c: c['c'])
            mgs = [c['tc'].find(HP+'cellMargin') if c['tc'].get('hasMargin') == '1' else im for c in rc]
            plan = cellsplit and split_plan([(c['h'] / 100, (int(g.get('top')) + int(g.get('bottom'))) / 100, c['rs'], s.text_bottom(c['tc'].find(HP+'subList')))
                                             for c, g in zip(rc, mgs)])      # '찬' 높은 행은 height 를 뺀다(hwp2html.split_plan)
            for k, c in enumerate(rc):
                tc = c['tc']; sub = tc.find(HP+'subList')
                bfid = tc.get('borderFillIDRef')
                mg = mgs[k]
                cst = [f'width:{pt(c["w"])}', '' if plan or s.free_text(sub, c['h']) else f'height:{pt(c["h"])}',
                       f'padding:{pt(mg.get("top"))} {pt(mg.get("right"))} {pt(mg.get("bottom"))} {pt(mg.get("left"))}',
                       'vertical-align:' + VALIGN.get(sub.get('vertAlign'), 'top')] + s.borders(bfid)
                f = s.fill(bfid)
                if f: cst.append(f'background-color:{f}')
                d = s.diagonal(bfid)
                if d: cst.append(d)
                span = (f' colspan="{c["cs"]}"' if c['cs'] > 1 else '') + (f' rowspan="{c["rs"]}"' if c['rs'] > 1 else '')
                ps = sub.findall(HP+'p')
                inner = ''.join(s.paragraph(p, tuple(t for t, on in (('top', i == 0), ('bottom', i == len(ps) - 1)) if on)) for i, p in enumerate(ps))
                out.append(f'<td{span} style="{";".join(x for x in cst if x)}">{inner}</td>')
            out.append('</tr>')
        if nh: out.append('</tbody>')
        out.append('</table>')
        return ''.join(out)

def convert(src, dst):
    SKIPPED.clear()
    head, secs = load(src)
    cv = Conv(head); blocks = []
    cv.z = zipfile.ZipFile(src)
    cv.bin_href = {i.get('id'): i.get('href') for i in etree.fromstring(cv.z.read('Contents/content.hpf')).iter('{http://www.idpf.org/2007/opf/}item')
                   if (i.get('href') or '').startswith('BinData/')}
    paras = [p for sec in secs for p in sec.findall(HP+'p')]
    blocks = []; prev_vp = None
    for p in paras:
        sg = p.find(HP+'linesegarray'); fst = sg[0] if sg is not None and len(sg) else None
        vp, vs = (int(fst.get('vertpos')), int(fst.get('vertsize'))) if fst is not None else (None, 0)
        pre = ''
        if cv.pend:
            if vp is not None and vs > 0 and vp > cv.pend['vp'] and vp + vs <= cv.pend['top']: cv.pend['end'] = max(cv.pend['end'], vp + vs)       # 표 위의 틈에 들어가는 문단: 표보다 먼저
            else: pre = cv.emit_pending()
        pg_start = ''
        if STORED_P and vp is not None and prev_vp is not None and vp < prev_vp and p.get('pageBreak') != '1': pg_start = '<div style="break-before:page"></div>'     # 저장된 줄 위치가 앞 문단보다 위로 되돌아가면 새 쪽
        if vp is not None: prev_vp = vp
        blocks.append(pg_start + pre + cv.paragraph(p, top=True))
    if cv.pend and blocks: blocks[-1] += cv.emit_pending()
    # 쪽 나누기 바로 앞이나 문서 맨 끝의 빈 문단은 눈에 안 보이는데, 쪽 끝에 아슬아슬하게 걸리면 빈 쪽을 하나 더 만든다(한컴은 들어가도 우리 글꼴 크기로는 넘침)
    empty = lambda b: re.fullmatch(r'<p style="[^"]*"><br></p>', b) is not None
    keep = [not (empty(b) and i + 1 < len(blocks) and paras[i + 1].get('pageBreak') == '1') for i, b in enumerate(blocks)]
    i = len(blocks) - 1
    while i > 0 and empty(blocks[i]): keep[i] = False; i -= 1       # 끝의 빈 문단이 여러 개면 모두 (첫 문단은 남김)
    blocks = [b for b, k in zip(blocks, keep) if k]
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
           'p,div{margin:0;orphans:1;widows:1}\np,div,td{white-space:pre-wrap;word-break:keep-all;overflow-wrap:break-word}\ntd>p,td>div{white-space:pre-wrap}\n'
           '.page{white-space:normal}\n'     # 문단 사이 줄바꿈 글자가 pre-wrap 에서 빈 줄 한 줄로 그려져 문단마다 14pt 가량 늘어나던 문제(쪽 수가 한컴의 2배가 되던 주원인)
           'td{box-sizing:border-box}\n'      # 칸의 height 는 안쪽 여백까지 포함한 값(HWPX cellSz). 기본값(content-box)이면 칸마다 여백만큼 커져서 표가 세로로 길어진다
           '@media print{body{background:#fff}.page{box-shadow:none;margin:0;padding:0;width:auto;min-height:0}}')
    n_body = len(blocks)
    for h in reversed(cv.hf['header']): blocks.insert(0, f'<div class="hwp-header">{h}</div>')
    for h in cv.hf['footer']: blocks.append(f'<div class="hwp-footer">{h}</div>')
    doc = (f'<!DOCTYPE html>\n<html lang="ko"><head><meta charset="utf-8">\n<title>{html.escape(title.strip())}</title>\n'
           f'<style>\n{css}\n</style></head>\n<body><div class="page">\n' + '\n'.join(blocks) + '\n</div></body></html>\n')
    open(dst, 'w', encoding='utf-8').write(doc)
    if SKIPPED: print(f'경고: 읽을 수 없는 그림 {len(SKIPPED)}개를 뺐습니다 (벡터·깨진 그림: {", ".join(sorted(set(SKIPPED)))})', file=sys.stderr)
    return n_body

if __name__ == '__main__':
    print(convert(sys.argv[1], sys.argv[2]), 'top-level paragraphs')

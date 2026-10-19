"""HWPX -> self-contained HTML (formatting expressed as standard inline CSS, units in pt)."""
import os, sys, zipfile, html, re, base64, io
from lxml import etree
from PIL import Image
import chartsvg
import wmf2svg
from hwp2html import old_hangul, _OLD_A, TBL_FIT, grad_css, BORDER_STYLE, crop_image, effect_image, PUA, HANGUL_DELTA, hangul_delta, space_delta, SPLIT_ON, split_plan, head_rows, spacing_css, keep_rows, heavy_css, mid_dot, BODY_BOTTOM      # 한컴 Wingdings/Symbol 글머리(U+F09F 등) -> 일반 유니코드. 브라우저는 사설 영역 문자를 못 그린다

from core import natural as _natural      # V3 1단계: 저장된 줄이 없는 문단의 줄 끊김을 우리가 계산한다(core/natural.py)
NATURAL = os.environ.get('NATURAL_BREAKS', 'on') != 'off'      # off 면 CSS 줄 나눔(V2 와 같은 동작)
IGNORE_LINESEG = os.environ.get('IGNORE_LINESEG') == '1'      # 시험용: 저장된 줄(linesegarray)을 무시한다
LANG_KEYS = (('hangul', 'HANGUL'), ('latin', 'LATIN'), ('hanja', 'HANJA'), ('japanese', 'JAPANESE'), ('other', 'OTHER'), ('symbol', 'SYMBOL'), ('user', 'USER'))
_SL = os.environ.get('STORED_LAYOUT', '')
PIDX = [0]      # 본문 문단 순번(core/vpos.py 가 문단을 가리키는 번호)
VZ = [0, 0]      # [저장된 줄 수, 줄 위치(vertpos)가 0 인 줄 수]: 낡은 파일은 위치를 안 채운다(core/vpos.py 가 이런 문서는 못 믿는다)
STORED = _SL in ('1', 'all', 'lines')       # 저장된 줄 끊김대로
STORED_P = _SL in ('1', 'all', 'pages')     # 저장된 쪽 시작대로      # 실험: 한컴이 저장한 줄 끊김·쪽 시작(linesegarray)을 그대로 따른다
MK = chr(1)         # 저장된 줄 시작 자리 표식(글 안)
LB = '<!--LB-->'    # 줄 사이 표식(부품 목록 안)
SKIPPED = []        # 읽지 못해 뺀 그림의 오류 이름(변환 끝에 경고로 알린다)
HX_LINE = {'SOLID': 'solid', 'DOT': 'dotted', 'DASH': 'dashed', 'DASH_DOT': 'dashed', 'DASH_DOT_DOT': 'dashed', 'LONG_DASH': 'dashed', 'CIRCLE': 'dotted', 'DOUBLE_SLIM': 'double', 'SLIM_THICK': 'double', 'THICK_SLIM': 'double', 'SLIM_THICK_SLIM': 'double'}      # lineShape style -> CSS
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

TAB_LEADER = {'1': 'solid', '2': 'dashed', '3': 'dotted', '4': 'dashed', '5': 'dotted', '6': 'dashed', '7': 'dotted'}


def tab_box(tab):
    """hp:tab: 한컴이 저장한 폭(width, HWPUNIT)과 채움선(leader: 1 실선·2 파선·3 점선…)대로 그린 인라인 상자. 목차의 점선 채움 + 오른쪽 쪽 번호가 이 모양이다."""
    w = int(tab.get('width') or 0) / 100; ld = TAB_LEADER.get(tab.get('leader') or '0', '')
    if w <= 0: return '&emsp;'
    return '<span style="display:inline-block;width:%gpt;height:0;vertical-align:baseline%s"></span>' % (w, ';border-bottom:1px %s #000' % ld if ld else '')


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
        s.shrink = 0; s.anchor_bottom = None
        s.wstack = [None]      # 문단이 놓인 칸의 글 폭(HWPUNIT). None = 본문 폭, 0 = 모름(자연 줄 끊김 계산 안 함)
        s._cs = {}; s.page = None
        s.pp = {p.get('id'): p for p in head.iter(HH+'paraPr')}
        s.numbering = {n.get('id'): n for n in head.iter(HH+'numbering')}
        s.bullets = {b.get('id'): b for b in head.iter(HH+'bullet') if b.get('useImage') != '1'}      # 글머리표 정의(hh:bullet char): 그림 글머리표는 안 한다
        s.numcount = {}
        s.page_css = ''; s.page_num = None
        s.hf = {'header': [], 'footer': []}          # 머리글·바닥글 본문(HTML). 본문 맨 앞/끝에 한 번 넣고, WeasyPrint(PDF)에서는 쪽 여백 상자의 running 요소로 쪽마다 되풀이한다(convert)
        s.hf_type = {'header': {}, 'footer': {}}     # 머리글·바닥글 HTML -> 적용 쪽(BOTH·ODD·EVEN)

    # ---------- style helpers ----------
    def fill(s, bfid):
        b = s.bf.get(bfid)
        if b is None: return None
        wb = b.find(f'{HC}fillBrush/{HC}winBrush')
        if wb is not None and wb.get('faceColor') not in (None, 'none'):
            return wb.get('faceColor')
        return None
    def grad(s, fb):
        """hc:fillBrush(또는 borderFill)의 그라데이션 채움(hc:gradation) -> CSS background 값. 선형·원형만(hwp2html.grad_css 와 같은 규칙), 아니면 None."""
        gr = fb.find(f'{HC}fillBrush/{HC}gradation') if fb is not None and fb.tag != f'{HC}fillBrush' else (fb.find(f'{HC}gradation') if fb is not None else None)
        if gr is None or gr.get('type') not in ('LINEAR', 'RADIAL'): return None
        cols = [c.get('value') for c in gr.findall(HC + 'color') if c.get('value')]
        if len(cols) < 2: return None
        return grad_css((int(gr.get('angle') or 0), cols, 2 if gr.get('type') == 'RADIAL' else 1, (int(gr.get('centerX') or 50), int(gr.get('centerY') or 50))))
    # 이미지 채움 모드(hc:imgBrush mode) -> (반복, 위치). TOTAL 은 칸에 맞춰 늘림(아래에서 크기를 100% 로)
    IMG_FILL = {'TILE': ('repeat', '0 0'), 'TILE_HORZ_TOP': ('repeat-x', 'left top'), 'TILE_HORZ_BOTTOM': ('repeat-x', 'left bottom'), 'TILE_VERT_LEFT': ('repeat-y', 'left top'),
                'TILE_VERT_RIGHT': ('repeat-y', 'right top'), 'TOTAL': ('no-repeat', '0 0'), 'CENTER': ('no-repeat', 'center'), 'CENTER_TOP': ('no-repeat', 'center top'),
                'CENTER_BOTTOM': ('no-repeat', 'center bottom'), 'LEFT_CENTER': ('no-repeat', 'left center'), 'LEFT_TOP': ('no-repeat', 'left top'), 'LEFT_BOTTOM': ('no-repeat', 'left bottom'),
                'RIGHT_CENTER': ('no-repeat', 'right center'), 'RIGHT_TOP': ('no-repeat', 'right top'), 'RIGHT_BOTTOM': ('no-repeat', 'right bottom')}
    def fill_img(s, bfid):
        """borderFill 의 이미지 채움(imgBrush) -> background-image 선언 목록. 자연 크기는 그림 해상도(DPI)로 정한다(hwp2html.fill_css 와 같은 규칙). 없거나 못 읽으면 []."""
        b = s.bf.get(bfid); ib = b.find(f'{HC}fillBrush/{HC}imgBrush') if b is not None else None
        ref = ib.find(HC + 'img') if ib is not None else None
        href = s.bin_href.get(ref.get('binaryItemIDRef')) if ref is not None else None
        mode = s.IMG_FILL.get(ib.get('mode')) if ib is not None else None
        if not href or not mode or href not in s.z.namelist() or s.z.getinfo(href).file_size > MAX_BIN_BYTES: return []
        try:
            im = Image.open(io.BytesIO(s.z.read(href)))
            dpi = (im.info.get('dpi') or (96, 96))[0] or 96
            w, h = im.size[0] * 72 / dpi, im.size[1] * 72 / dpi
            alpha = im.mode in ('RGBA', 'LA') or 'transparency' in im.info
            im = im.convert('RGBA' if alpha else 'RGB')
            im = effect_image(im, int(ref.get('bright') or 0), int(ref.get('contrast') or 0), {'GRAY_SCALE': 1, 'BLACK_WHITE': 2}.get(ref.get('effect'), 0))      # 밝기·대비·효과(쪽 배경 그림 HWP5-nopassword: 밝기 50·대비 -15)
            im.thumbnail((1400, 1400))
            buf = io.BytesIO(); im.save(buf, 'PNG' if alpha else 'JPEG', **({} if alpha else {'quality': 85}))
        except Exception as e:
            SKIPPED.append(type(e).__name__); return []
        uri = f'data:image/{"png" if alpha else "jpeg"};base64,{base64.b64encode(buf.getvalue()).decode()}'
        size = '100% 100%' if ib.get('mode') == 'TOTAL' else f'{w:.2f}pt {h:.2f}pt'
        return [f'background-image:url({uri})', f'background-repeat:{mode[0]}', f'background-position:{mode[1]}', f'background-size:{size}']
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
        if dg is None or dg.get('type') in (None, 'NONE'): return None      # 선 모양(diagonal)이 없으면 slash·backSlash 가 있어도 한컴은 안 그린다(결재 문서 표지 22건: 한컴 PDF 에 대각선 없음)
        cl = b.get('centerLine')      # 칸 가운데 줄(중심선): 선 모양은 diagonal 의 것. VERTICAL = 세로 가운데에 놓인 가로 막대(추진일정 간트 막대: 2.0mm 색 선), HORIZONTAL = 가로 가운데의 세로선, CROSS = 둘 다
        if cl in ('VERTICAL', 'HORIZONTAL', 'CROSS'):
            wmm = float(dg.get('width', '0.12 mm').split()[0]); col = dg.get('color', '#000000'); hw = f'{max(wmm / 2, 0.15):g}mm'
            line = lambda d: f'linear-gradient({d},transparent calc(50% - {hw}),{col} calc(50% - {hw}),{col} calc(50% + {hw}),transparent calc(50% + {hw}))'
            if cl in ('VERTICAL', 'CROSS'): grads.append(line('to bottom'))
            if cl in ('HORIZONTAL', 'CROSS'): grads.append(line('to right'))
        for tag, direction in (('backSlash', 'to top right'), ('slash', 'to bottom right')):
            e = b.find(HH+tag)
            if e is not None and e.get('type') not in (None, 'NONE'):
                wmm = float(dg.get('width', '0.12 mm').split()[0])
                col = dg.get('color', '#000000')
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
        else: st += heavy_css(fams[0] if fams else '', False)
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
        hd = 0 if half else hangul_delta(fams[0] if fams else '') * ra / 100
        # 한컴 글꼴 대 나눔 글꼴의 한글 폭 차이 보정(hwp2html.HANGUL_DELTA)과 공백 폭 보정(space_delta, HWP 와 같은 식)은 PDF 에서만 더한다. 글꼴 자체 공백을 쓰는 글자 모양(useFontSpace)은 공백 보정 제외
        st += spacing_css((sp + ra - 100) / (200 if half else 100), hd, 0 if c.get('useFontSpace') == '1' else space_delta(fams[-1] if half and fams else fams[0] if fams else '', half, hd, ra / 100, sp))
        if c.find(HH+'supscript') is not None: st.append('vertical-align:super;font-size:58%;line-height:0')
        if c.find(HH+'subscript') is not None: st.append('vertical-align:sub;font-size:58%;line-height:0')
        return ';'.join(st)
    def para_css(s, pid, p_el, first_cid, trim=(), top=False):
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
            st += s.fill_img(b.get('borderFillIDRef'))
        bs = p.find(HH+'breakSetting')
        if bs is not None and bs.get('breakNonLatinWord') == 'KEEP_WORD': st.append('word-break:normal')      # 한컴: KEEP_WORD = 글자 단위(한글 음절 사이·영어는 낱말째 = CSS 기본값), BREAK_WORD = 어절 단위(스키마 이름과 반대; hwp2html bw 주석 참고)
        if bs is not None and bs.get('widowOrphan') == '1': st.append('orphans:2;widows:2')
        if top and p_el.get('pageBreak') == '1': st.append('break-before:page')       # 표 칸·글상자 안 문단의 쪽 나누기 표시는 한컴이 무시한다
        if first_cid is not None:     # default font for empty lines / table-only paragraphs
            c = s.cp[first_cid]
            st.append(f'font-size:{pt(c.get("height"))}')
            st.append('font-family:' + "'" + s.fonts['HANGUL'][c.find(HH+'fontRef').get('hangul')] + "'")
        return ';'.join(st)
    def number_prefix(s, pid):
        h = s.pp[pid].find(HH+'heading'); s.bullet_cid = None
        if h is not None and h.get('type') == 'BULLET':      # 글머리표 문단(추진일정 표 캡션의 ※): 정의의 글자를 앞에 붙인다(예전엔 NUMBER 만 읽어 빠졌다)
            b = s.bullets.get(h.get('idRef')); ch = (b.get('char') or '') if b is not None else ''
            ph = b.find(HH+'paraHead') if b is not None else None
            if ph is not None and ph.get('charPrIDRef') in s.cp: s.bullet_cid = ph.get('charPrIDRef')      # 글머리표 자신의 글자 모양(색·크기: pr-1674 의 파란 ●)
            return html.escape(ch.translate(PUA), quote=False) + ' ' if ch.strip() else ''
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
        """그림 한 개. 그림 파일이 없거나 못 읽는 글자처럼 취급 그림(문서 속 그림을 지운 '마스킹' 문서 등)도 한컴처럼 자리(줄 높이·폭)는 남긴다 — 빈 상자."""
        r = s._picture(pic)
        pos = pic.find(HP + 'pos')
        if r and pos is not None and pos.get('treatAsChar') != '1' and pic.get('textWrap') in ('SQUARE', 'TIGHT') and pos.get('horzAlign') in ('LEFT', 'RIGHT') and pos.get('horzRelTo') in ('COLUMN', 'PARA') and len(s.wstack) == 1 and r.startswith('<img'):
            r = s.sq_wrap(r, (pos.get('horzAlign'), int(pos.get('horzOffset') or 0) / 100, int(pos.get('vertOffset') or 0) / 100 if pos.get('vertRelTo') == 'PARA' else 0))      # 글 감싸기(네모): 그림이 한쪽에 떠 있고 글이 옆으로 흐른다
        if r: return r
        pos = pic.find(HP + 'pos'); sz = pic.find(HP + 'curSz')
        if pos is None or pos.get('treatAsChar') != '1': return ''
        if sz is None or not (int(sz.get('width') or 0) > 0 and int(sz.get('height') or 0) > 0): sz = pic.find(HP + 'sz')
        if sz is None or not (int(sz.get('width') or 0) > 0 and int(sz.get('height') or 0) > 0): return ''
        return f'<span style="display:inline-block;width:{pt(sz.get("width"))};height:{pt(sz.get("height"))};vertical-align:bottom"></span>'

    def _picture(s, pic):
        """hp:pic -> <img data URI>. BMP·큰 파일은 웹용 JPEG(최대 1600px)로 줄인다. 크기는 curSz를 pt로 그대로 둔다(html2hwpx가 되읽음)."""
        ref = pic.find(HC + 'img')
        href = s.bin_href.get(ref.get('binaryItemIDRef')) if ref is not None else None
        if not href or href not in s.z.namelist() or s.z.getinfo(href).file_size > MAX_BIN_BYTES: return ''
        data = s.z.read(href)
        svg = wmf2svg.vector_svg(data, href.rsplit('.', 1)[-1])      # SVG 는 그대로, WMF 는 SVG 로 바꿔 넣는다(rhwp 도 data:image/svg+xml)
        if svg is not None: mime, data = 'svg+xml', svg.encode('utf-8')
        else:
          try:        # 읽을 수 없는 그림(EMF·깨진 파일) 한 장 때문에 문서 전체 변환이 실패하지 않게 뺀다
            im = Image.open(io.BytesIO(data)); fmt = (im.format or '').lower()
            eff = (int(ref.get('bright') or 0), int(ref.get('contrast') or 0), {'GRAY_SCALE': 1, 'BLACK_WHITE': 2}.get(ref.get('effect'), 0))      # 밝기·대비·효과(hc:img)
            cl = pic.find(HP + 'imgClip'); clip = tuple(int(cl.get(k) or 0) for k in ('left', 'top', 'right', 'bottom')) if cl is not None else (0, 0, 0, 0)      # 자르기(HWPUNIT, 75=1px)
            dm = pic.find(HP + 'imgDim'); ref = (int(dm.get('dimwidth') or 0), int(dm.get('dimheight') or 0)) if dm is not None else None
            cropped = crop_image(im, *clip, ref=ref)
            if fmt in ('jpeg', 'png', 'gif') and len(data) <= WEB_IMG_BYTES and eff == (0, 0, 0) and cropped is im: mime = fmt
            else:
                im = effect_image(cropped.convert('RGBA') if cropped.mode in ('RGBA', 'LA', 'P') else cropped.convert('RGB'), *eff)
                if im.mode in ('RGBA', 'LA', 'P'):      # 투명 배경은 흰색으로
                    im = im.convert('RGBA'); bg = Image.new('RGB', im.size, 'white'); bg.paste(im, mask=im.split()[3]); im = bg
                im = im.convert('RGB'); im.thumbnail((1600, 1600))
                buf = io.BytesIO(); im.save(buf, 'JPEG', quality=85, optimize=True); data, mime = buf.getvalue(), 'jpeg'
          except Exception as e:
            SKIPPED.append(type(e).__name__); return ''
        sz = next((e for e in (pic.find(HP + 'curSz'), pic.find(HP + 'sz')) if e is not None and int(e.get('width') or 0) > 0 and int(e.get('height') or 0) > 0), None)
        if sz is None:      # 묶음 속 그림은 curSz 가 0 이고 sz 도 없다: 현재 크기 = 회전 중심(centerX·centerY)의 2배(한컴 PDF 실측: 로고 68.6×23.9·배너 277.7×37.2·OPEN 89.5×31.6 = 중심×2). 그것도 없으면 원본 크기
            ri = pic.find(HP + 'rotationInfo'); cw, chh = (int(ri.get('centerX') or 0), int(ri.get('centerY') or 0)) if ri is not None else (0, 0)
            sz = {'width': str(2 * cw), 'height': str(2 * chh)} if cw > 0 and chh > 0 else None      # Element 처럼 .get 으로 읽는 값
        if sz is None: sz = next((e for e in (pic.find(HP + 'orgSz'),) if e is not None and int(e.get('width') or 0) > 0 and int(e.get('height') or 0) > 0), None)      # curSz 가 0 인 그림(hp:sz·orgSz 에 크기가 있음)도 그린다
        if sz is None: return ''
        alt = html.escape(((pic.findtext(HP + 'shapeComment') or '').strip().splitlines() or [''])[0], quote=True)
        return (f'<img src="data:image/{mime};base64,{base64.b64encode(data).decode()}" alt="{alt}" '
                f'style="width:{pt(sz.get("width"))};height:{pt(sz.get("height"))}">')

    def container(s, ct, depth=0):
        """hp:container(개체 묶음) -> 묶음 틀(hp:sz) 안에 속 그림·글상자·묶음을 각자 자리에(hwp2html.group_gso 와 같음). 속 개체의 자리 = 자기 renderingInfo 의 이동 행렬(transMatrix e3·e6, 묶음 좌표 HWPUNIT),
        크기 = curSz(0 이면 orgSz). 예전엔 묶음이 통째로 빠져 쪽 아래 로고 배너(taxi_press 지책브레피·OPEN)가 안 나왔다."""
        sz = ct.find(HP + 'sz')
        w, h = (int(sz.get('width')), int(sz.get('height'))) if sz is not None else (0, 0)
        if not (w and h):
            o = ct.find(HP + 'orgSz'); w, h = (int(o.get('width')), int(o.get('height'))) if o is not None else (0, 0)
        if not (w and h) or depth > 4: return ''
        out = []
        for ch in ct:
            tag = etree.QName(ch).localname
            if tag not in ('pic', 'container', 'rect'): continue
            tm = ch.find(f'{HP}renderingInfo/{HC}transMatrix')
            tx, ty = (float(tm.get('e3')), float(tm.get('e6'))) if tm is not None else (0.0, 0.0)
            if tag == 'pic': inner = s.picture(ch)
            elif tag == 'container': inner = s.container(ch, depth + 1)
            else:
                dt = ch.find(HP + 'drawText'); sub = dt.find(HP + 'subList') if dt is not None else None
                inner = ''.join(s.paragraph(q) for q in sub.findall(HP + 'p')) if sub is not None else ''
            if inner: out.append(f'<div style="position:absolute;left:{tx / 100:g}pt;top:{ty / 100:g}pt">{inner}</div>')
        pos = ct.find(HP + 'pos'); inline = pos is not None and pos.get('treatAsChar') == '1'
        return f'<div style="position:relative;width:{w / 100:g}pt;height:{h / 100:g}pt;{"display:inline-block;vertical-align:top" if inline else "display:block"}">{"".join(out)}</div>' if out else ''

    def chart(s, cht):
        """hp:chart(OOXML 차트: chartIDRef 가 Chart/chartN.xml) -> 인라인 SVG. 크기는 hp:sz(HWPUNIT). 못 그리면 빈 글(예전처럼)."""
        ref, sz = cht.get('chartIDRef'), cht.find(HP + 'sz')
        if not ref or ref not in s.z.namelist() or sz is None: return ''
        try: svg = chartsvg.render(s.z.read(ref), int(sz.get('width')) / 100, int(sz.get('height')) / 100)
        except Exception as e: SKIPPED.append(type(e).__name__); return ''
        return f'<span style="display:inline-block;vertical-align:top;line-height:0">{svg}</span>' if svg else ''

    # ---------- content ----------
    def text_of(s, t, brk=None):
        out = []

        def put(txt):
            if not brk: out.append(html.escape(old_hangul(txt), quote=False).translate(PUA)); return
            units, k = [], 0      # 옛한글 아래아 음절은 한 글자로 합치되 저장된 줄 위치(textpos)는 원래 글자 수로 센다
            while k < len(txt):
                m = _OLD_A.match(txt, k)
                if m: units.append((old_hangul(m.group(0)), len(m.group(0)))); k = m.end()
                else: units.append((txt[k], 1)); k += 1
            for c, n in units:        # \uc800\uc7a5\ub41c \uc904 \uc2dc\uc791 \uc704\uce58(textpos)\ub294 \ubb38\ub2e8 \uae00\uc790 \uc218(\uc81c\uc5b4 \uc694\uc18c 1\uce78\uc529)\ub85c \uc13c \uac12 \u2014 \uadf8 \uc790\ub9ac\uc5d0 \ud45c\uc2dd MK \ub97c \ub454\ub2e4
                if any(q in brk['set'] for q in range(brk['pos'], brk['pos'] + n)): out.append(MK)
                out.append(html.escape(c, quote=False).translate(PUA)); brk['pos'] += n
        put(t.text or '')
        for ch in t:
            tag = etree.QName(ch).localname
            if tag == 'lineBreak': out.append('<br>')
            elif tag == 'fwSpace': out.append('\u2007')
            elif tag == 'nbSpace': out.append('\u00a0')
            elif tag == 'tab': out.append(tab_box(ch))
            elif tag == 'hyphen': out.append('-')
            if brk and tag in ('lineBreak', 'fwSpace', 'nbSpace', 'tab', 'hyphen'): brk['pos'] += 1
            put(ch.tail or '')
        return ''.join(out)

    def paragraph(s, p, trim=(), top=False):
        runs = p.findall(HP+'run')
        first_cid = runs[0].get('charPrIDRef') if runs else None
        parts = []; has_table = False
        brk = single = None
        mk = not STORED      # HTML 내보내기: 저장된 줄 정보를 hwp-lp 클래스로 담아 두고 PDF 단계(convert.PDF_CSS)에서만 켠다(저장 모드는 예전처럼 인라인 스타일)
        if True:
            sg0 = p.find(HP+'linesegarray')
            s.shrink = 0
            if top: s.anchor_bottom = (int(sg0[0].get('vertpos') or 0) + int(sg0[0].get('vertsize') or 0)) / 100 if sg0 is not None and len(sg0) else None      # 앵커 문단 첫 줄 아래 끝(쪽 안 y, pt) — 쪽 아래 정렬 표가 글과 겹치는지 보려고
            if top and s.page is None and p.find('.//' + HP + 'secPr') is not None: s.section(p.find('.//' + HP + 'secPr'))      # 구역 첫 문단: 쪽 크기를 먼저 안다
            if top and s.page and sg0 is not None and len(sg0) and p.find('.//'+HP+'tbl') is not None:
                body_h = (s.page['h'] - s.page['top'] - s.page['bottom']) / 100; lh_ = int(sg0[0].get('vertsize') or 0) / 100
                if body_h < lh_ <= body_h + 30 and len(sg0) == 1: s.shrink = lh_ - body_h + 0.5      # 본문보다 높은 한 줄: 한컴은 넘쳐 그린다
            prefix = s.number_prefix(p.get('paraPrIDRef'))      # 번호 카운터가 늘어나는 부작용이 있어 한 번만 부른다(자연 줄 끊김이 접두 폭을 알려고 먼저 필요)
            simple = not any(True for _ in p.iter(HP+'tbl', HP+'pic', HP+'rect', HP+'chart', HP+'lineBreak', HP+'tab'))
            if sg0 is not None and len(sg0) and all(int(l.get('vertsize') or 0) > 0 for l in sg0) and simple and not IGNORE_LINESEG:
                if len(sg0) == 1: single = True
                else: brk = {'pos': 0, 'set': {int(l.get('textpos')) for l in sg0[1:]}}
            elif NATURAL and simple:
                sp_ = p.find('.//' + HP + 'secPr')
                if sp_ is not None and s.page is None: s.section(sp_)      # 구역 첫 문단: 쪽 폭을 먼저 알아야 한다
                nb = s.natural_brk(p, runs, prefix)
                if nb: brk = {'pos': 0, 'set': nb}
        if prefix and first_cid: parts.append(f'<span style="{s.char_css(getattr(s, "bullet_cid", None) or first_cid)}">{prefix}</span>')
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
                if brk and tag in ('secPr', 'ctrl'): brk['pos'] += 8       # 확장 제어(구역·단 정의·머리말·쪽 번호·책갈피·필드…)는 HWP5 처럼 textpos 에서 8칸을 차지한다(저장된 줄 시작 52 대 글자 수 44 로 확인)
                if tag == 't': buf += s.text_of(ch, brk)
                elif tag == 'tbl': flush(); parts.append(s.table(ch)); has_table = True
                elif tag == 'pic': flush(); parts.append(s.picture(ch))
                elif tag == 'container': flush(); parts.append(s.container(ch))
                elif tag == 'switch':      # hp:switch: ooxmlchart case 의 hp:chart 를 그린다(default 의 OLE 대체본은 못 그린다)
                    cs = ch.find(HP+'case'); cht = cs.find(HP+'chart') if cs is not None else None
                    if cht is not None: flush(); parts.append(s.chart(cht))
                elif tag == 'secPr': s.section(ch)
                elif tag == 'ctrl':
                    pn = ch.find(HP+'pageNum')
                    if pn is not None: s.page_num = pn
                    for kind in ('header', 'footer'):
                        hf = ch.find(HP+kind)
                        sub = hf.find(HP+'subList') if hf is not None else None
                        if sub is not None:
                            s.wstack.append(None)      # 머리말·꼬리말 글 폭 = 본문 폭
                            try: h = ''.join(s.paragraph(q) for q in sub.findall(HP+'p'))
                            finally: s.wstack.pop()
                            if h and h not in s.hf[kind]: s.hf[kind].append(h); s.hf_type[kind][h] = hf.get('applyPageType') or 'BOTH'       # 홀·짝 쪽이 서로 다르면 둘 다, 같으면 한 번만
                elif tag in ('checkBtn', 'radioBtn', 'btn'):    # 서식의 양식 컨트롤: 모양은 못 그리고 기호 + 설명 글만 남긴다
                    mark = {'checkBtn': ('☐', '☑'), 'radioBtn': ('○', '◉')}.get(tag)
                    buf += html.escape((mark[ch.get('value') == 'CHECKED'] + ' ' if mark else '') + (ch.get('caption') or ''), quote=False)
                elif tag == 'rect':                              # 글상자: 안의 글만 가져온다(도형 모양·테두리는 무시)
                    dt = ch.find(HP+'drawText'); sub = dt.find(HP+'subList') if dt is not None else None
                    if sub is not None:
                        flush(); has_table = True                # <p> 안에 <div> 를 넣을 수 없어 바깥도 <div> 로
                        szr = ch.find(HP+'sz'); tm = dt.find(HP+'textMargin')
                        s.wstack.append(max(int(szr.get('width')) - int(tm.get('left') or 0) - int(tm.get('right') or 0), 0) if szr is not None and tm is not None and sub.get('textDirection', 'HORIZONTAL') == 'HORIZONTAL' else 0)
                        bx = ['display:inline-block', 'vertical-align:top', 'box-sizing:border-box']
                        cz = ch.find(HP+'curSz'); fbr = ch.find(HC+'fillBrush'); ls = ch.find(HP+'lineShape')
                        if cz is not None and int(cz.get('width') or 0) and int(cz.get('height') or 0): bx += [f'width:{int(cz.get("width")) / 100:g}pt', f'min-height:{int(cz.get("height")) / 100:g}pt']      # 글상자 크기(개체 크기)
                        wbr = fbr.find(HC+'winBrush') if fbr is not None else None
                        if wbr is not None and wbr.get('faceColor') not in (None, 'none'): bx.append('background:' + wbr.get('faceColor'))
                        elif fbr is not None and s.grad(fbr): bx.append('background:' + s.grad(fbr))      # 분홍 방사형 큰 글상자(d-pi4-import)
                        if ls is not None and ls.get('style') not in (None, 'NONE') and int(ls.get('width') or 0) > 0: bx.append(f'border:{max(int(ls.get("width")) / 100, 0.5):g}pt {HX_LINE.get(ls.get("style"), "solid")} {ls.get("color") or "#000000"}')
                        try: parts.append('<div class="tb" style="%s">' % ';'.join(bx) + ''.join(s.paragraph(q) for q in sub.findall(HP+'p')) + '</div>')
                        finally: s.wstack.pop()
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
        style = s.para_css(p.get('paraPrIDRef'), p, first_cid, () if has_table else trim, top)
        if (brk or single) and not has_table and parts:
            just = 'text-align-last:justify;' if 'text-align:justify' in style else ''
            if single: parts = ['<span class="hwp-lp">' + ''.join(parts) + '</span>'] if mk else ['<span style="display:block;white-space:pre">' + ''.join(parts) + '</span>']
            else:
                lines = [[]]
                for x in parts:
                    if x == LB: lines.append([])
                    else: lines[-1].append(x)
                cur_ = re.search(r'padding-left:(-?[\d.]+)pt', style); cur_ = float(cur_.group(1)) if cur_ else 0.0
                def wrap_pl(k):      # 떠 있는 개체 옆으로 흐르는 줄(글 감싸기): 한컴이 저장한 줄 시작 x(horzpos)가 문단 왼쪽보다 크면 그만큼 안쪽에서 시작한다
                    if sg0 is None or k >= len(sg0) or 'text-indent' in style: return ''
                    hz = int(sg0[k].get('horzpos') or 0) / 100
                    return f'padding-left:{hz - cur_:g}pt;' if hz > 20 and hz - cur_ > 10 else ''
                if mk: parts = ['<span class="hwp-lp%s">%s</span>' % (' hwp-lj' if just and k != len(lines) - 1 else '', ''.join(l) or '&nbsp;') for k, l in enumerate(lines)]
                else: parts = ['<span style="display:block;white-space:pre;%s%s">%s</span>' % (wrap_pl(k), '' if k == len(lines) - 1 else just, ''.join(l) or '&nbsp;') for k, l in enumerate(lines)]
        n_tb = sum(x.startswith('<table') for x in parts)
        if n_tb > 1 and all(x.startswith('<table') or not ('<img' in x or re.sub(r'<[^>]+>|\s', '', x)) for x in parts):
            parts = [x.replace(';display:inline-table;vertical-align:top', ';display:inline-table;vertical-align:bottom', 1) for x in parts if x.startswith('<table')]      # 글자처럼 취급 개체는 줄의 기준선(맨 아래)에 앉는다. 한 문단에 글자처럼 취급 표가 여럿이면 한컴처럼 한 줄에 나란히(inline-table 그대로; 사이의 빈 글은 뺀다 — 결재란 두 개가 위아래로 쌓이던 결함)
        elif has_table and all(x.startswith('<table') or not ('<img' in x or re.sub(r'<[^>]+>|\s', '', x)) for x in parts):
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
        pidx = None
        if top: pidx = PIDX[0]; PIDX[0] += 1
        if STORED and top and sg0 is not None:      # 본문 최상위 문단의 줄만(칸 안 줄은 칸마다 0 에서 다시 시작한다)
            for ln in sg0: VZ[0] += 1; VZ[1] += int(ln.get('vertpos') or 0) == 0
        if has_table: return f'<div style="{style}">{body}</div>'
        vpa = ''
        if STORED and top and sg0 is not None and len(sg0) and int(sg0[0].get('vertsize') or 0) > 0 and first_cid in s.cp:      # 2패스 vpos 되잡기 표시(hwp2html.render_para 와 같음): 한컴 저장 첫 줄 세로 위치(pt)·줄 상자 위 반 줄 간격(px)
            fs_px = int(s.cp[first_cid].get('height')) / 100 * 4 / 3
            ml = re.search(r'line-height:(-?[\d.]+)(pt)?', style)
            lh_px = (float(ml.group(1)) * (4 / 3 if ml.group(2) else fs_px)) if ml else fs_px
            vpa = f' data-pi="{pidx}" data-vp="{int(sg0[0].get("vertpos")) / 100:.2f}" data-ho="{(lh_px - fs_px) / 2:.2f}"'
        return f'<p{vpa} style="{style}">{body or "<br>"}</p>'

    def body_w(s):
        return s.page['w'] - s.page['left'] - s.page['right'] if s.page else 0

    def charstyle(s, cid):
        """hwp2html.charshapes 항목과 같은 모양(core/widthmodel 이 읽는다): 크기 pt, 언어 칸 7개마다 글꼴·장평·자간·상대 크기, 굵게·기울임·'글꼴에 어울리는 빈칸'."""
        if cid in s._cs: return s._cs[cid]
        c = s.cp[cid]; fr = c.find(HH+'fontRef'); ra = c.find(HH+'ratio'); sp = c.find(HH+'spacing'); rs = c.find(HH+'relSz')
        langs = []
        for k, ff in LANG_KEYS:
            face = s.fonts.get(ff, {}).get(fr.get(k)) if fr is not None else None
            langs.append(dict(face=face, ratio=int(ra.get(k) or 100) or 100 if ra is not None else 100, spacing=int(sp.get(k) or 0) if sp is not None else 0, rel=int(rs.get(k) or 100) or 100 if rs is not None else 100, pos=0))
        s._cs[cid] = r = dict(size=int(c.get('height')) / 100, langs=langs, bold=c.find(HH+'bold') is not None, italic=c.find(HH+'italic') is not None, ufs=c.get('useFontSpace') == '1')
        return r

    def natural_brk(s, p, runs, prefix=''):
        """저장된 줄이 없는 글 문단의 줄 시작 위치 집합(text_of 의 textpos 규칙과 같은 위치). 못 계산하면 None(CSS 줄 나눔)."""
        w = s.wstack[-1]
        if w is None: w = s.body_w()
        pp = s.pp.get(p.get('paraPrIDRef'))
        if not w or not runs or pp is None: return None
        pos = 0; chars = []; cids = {}

        def add(txt, cid):
            nonlocal pos
            for ch_ in txt: chars.append((pos, ch_)); cids[pos] = cid; pos += 1
        for r in runs:
            cid = r.get('charPrIDRef')
            if cid not in s.cp: return None
            for ch in r:
                tag = etree.QName(ch).localname
                if tag in ('secPr', 'ctrl'): pos += 8; continue
                if tag != 't': continue
                add(ch.text or '', cid)
                for sub_ in ch:
                    t2 = etree.QName(sub_).localname
                    if t2 == 'fwSpace': add('\u2007', cid)
                    elif t2 == 'nbSpace': add('\u00a0', cid)
                    elif t2 == 'hyphen': add('-', cid)
                    else: return None      # lineBreak·tab 등: CSS 에 맡김
                    add(sub_.tail or '', cid)
        if not chars: return None
        case = pp.find(f'{HP}switch/{HP}case'); box = case if case is not None else pp
        mg = box.find(HH+'margin')
        if mg is None: return None
        left, right, ind = (int(mg.find(HC+n).get('value')) for n in ('left', 'right', 'intent'))
        bs = pp.find(HH+'breakSetting'); ku = bs is not None and bs.get('breakNonLatinWord') == 'KEEP_WORD'      # 한컴: KEEP_WORD = 글자 단위
        return _natural.natural_breaks(chars, lambda q: s.charstyle(cids[q]), ku, ind * 2, w - left - right, prefix=prefix, cond=int(pp.get('condense') or 0)) or None

    def section(s, sec):
        pg = sec.find(HP+'pagePr'); m = pg.find(HP+'margin'); g = lambda k: int(m.get(k))
        w, h = int(pg.get('width')), int(pg.get('height'))
        if pg.get('landscape') == 'NARROWLY': w, h = h, w
        s.page = dict(w=w, h=h, top=g('top')+g('header'), mtop=g('top'), bottom=g('bottom')+g('footer'), foot=g('footer'), left=g('left')+g('gutter'), right=g('right'))
        pbf = next((e for e in sec.iter(HP+'pageBorderFill') if e.get('type') == 'BOTH'), None) or next(iter(sec.iter(HP+'pageBorderFill')), None)
        of = pbf.find(HP+'offset') if pbf is not None else None
        if pbf is not None and of is not None and not getattr(s, 'pbf', None): s.pbf = dict(bf=pbf.get('borderFillIDRef'), paper=pbf.get('textBorder') == 'CONTENT', off=tuple(int(of.get(k) or 0) for k in ('left', 'right', 'top', 'bottom')), area=pbf.get('fillArea', 'PAPER'), vis=next(((v.get('border') or 'SHOW_ALL', v.get('fill') or 'SHOW_ALL') for v in sec.iter(HP+'visibility')), ('SHOW_ALL', 'SHOW_ALL')))      # 쪽 테두리·배경: 첫 구역 것만. textBorder 는 이름과 달리 한컴이 PAPER → 본문 가장자리(+offset 바깥)·CONTENT → 종이 가장자리(+offset 안쪽)에 그린다(HWP5-nopassword·native-8-0 PAPER: 본문 기준 70.9·21.8pt, condense_* CONTENT: 종이 기준 14.2pt 로 확인). fillArea = 채움이 깔리는 곳(PAPER 종이·PAGE 본문·BORDER 테두리 안쪽)

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

    def shrink_rows(s, cells, shrink, last_only=False):
        """쪽 본문보다 높은 한 줄(글자처럼 취급 표 하나뿐인 문단)은 한컴이 그 쪽에 그대로 두고 아래로 넘쳐 그린다. 우리는 표를 행 경계에서 갈라 마지막 행이 다음 쪽으로 가므로(표지 +1쪽),
        넘치는 만큼(shrink pt)을 글 높이보다 여유가 가장 큰 행의 칸 높이 지정에서 덜어 한 쪽에 들어가게 한다. 글이 차지하는 높이(저장된 줄 정보)보다 작게는 안 줄인다."""
        rows = {}
        for c in cells: rows.setdefault(c['r'], []).append(c)
        slack = {}
        for r, cs in rows.items():
            if any(c['rs'] != 1 for c in cs): continue
            need = 0
            for c in cs:
                sub = c['tc'].find(HP+'subList'); tb = s.text_bottom(sub)
                if not tb: need = None; break
                mg = c['tc'].find(HP+'cellMargin')
                need = max(need, tb * 100 + (int(mg.get('top')) + int(mg.get('bottom')) if mg is not None else 0))
            if need is not None and (not last_only or r == max(rows)): slack[r] = max(c['h'] for c in cs) - need
        left = shrink * 100
        for r in sorted(slack, key=lambda r: -slack[r]):
            cut = min(left, slack[r] * 0.8)
            if cut <= 0: break
            for c in rows[r]: c['h'] = int(c['h'] - cut)
            left -= cut
            if left <= 0: break

    def page_bottom_xy(s, pos, w, h):
        """쪽(본문 영역)·종이 아래에 붙은 떠 있는 표(공문 맨 아래 '시행·우편번호·전화' 상자)의 본문 영역 안 좌표(pt). 앵커 문단 글과 겹치면 None(흐름대로 둔다)."""
        pg = s.page; bw = (pg['w'] - pg['left'] - pg['right']) / 100; bh = (pg['h'] - pg['top'] - pg['bottom']) / 100
        vo = int(pos.get('vertOffset') or 0); vo = (vo - (1 << 32) if vo >= (1 << 31) else vo) / 100
        ho = int(pos.get('horzOffset') or 0); ho = (ho - (1 << 32) if ho >= (1 << 31) else ho) / 100
        y = bh - h - vo if pos.get('vertRelTo') == 'PAGE' else (pg['h'] / 100 - h - vo) - pg['top'] / 100
        ha = pos.get('horzAlign'); base = 0 if pos.get('horzRelTo') in ('PAGE', 'COLUMN', 'PARA') else -pg['left'] / 100
        lo, hi = base, base + (bw if base == 0 else pg['w'] / 100)
        x = lo + ho if ha == 'LEFT' else lo + (hi - lo - w) / 2 + ho if ha == 'CENTER' else hi - w - ho
        if s.anchor_bottom is not None and s.anchor_bottom > y + 0.5: return None
        return x, y

    def sq_wrap(s, html_, sq):
        """글 감싸기(네모) 개체: 높이 0 인 상자 안에 절대 위치로 떠 있게 한다(왼쪽 정렬이면 왼쪽에서 ho, 오른쪽이면 오른쪽에서 ho)."""
        if not sq: return html_
        side, ho, vo = sq
        return '<div style="position:relative;height:0"><div style="position:absolute;top:%gpt;%s:%gpt">%s</div></div>' % (vo, 'left' if side == 'LEFT' else 'right', ho, html_)

    def fo_wrap(s, html_, fo):
        return html_ if not fo else '<div class="fo" style="--cx:%gpt;--cy:%gpt;--px:%gpt;--py:%gpt">%s</div>' % (fo[0], fo[1], fo[0] + s.page['left'] / 100, fo[1] + s.page['top'] / 100, html_)

    def table(s, tbl):
        sz = tbl.find(HP+'sz'); pos = tbl.find(HP+'pos'); om = tbl.find(HP+'outMargin'); im = tbl.find(HP+'inMargin')
        ncol = int(tbl.get('colCnt'))
        cells = []
        shrink, s.shrink = s.shrink, 0      # 바깥 표에만(칸 안 표는 0)
        for tr in tbl.findall(HP+'tr'):
            for tc in tr.findall(HP+'tc'):
                a = tc.find(HP+'cellAddr'); sp = tc.find(HP+'cellSpan'); csz = tc.find(HP+'cellSz')
                cells.append(dict(tc=tc, r=int(a.get('rowAddr')), c=int(a.get('colAddr')), cs=int(sp.get('colSpan')),
                                  rs=int(sp.get('rowSpan')), w=int(csz.get('width')), h=int(csz.get('height')), hd=int(tc.get('header') == '1')))
        if shrink > 0: s.shrink_rows(cells, shrink)
        elif TBL_FIT:      # 표 개체 높이(hp:sz)가 행 높이 합보다 작으면 한컴은 맨 아래 행을 그만큼 줄여 그린다(hwp2html.render_table 과 같음)
            rh = {}
            for c_ in cells:
                if c_['rs'] == 1: rh[c_['r']] = max(rh.get(c_['r'], 0), c_['h'])
            ex = sum(rh.values()) - int(sz.get('height') or 0) if sz is not None and len(rh) == len({c_['r'] for c_ in cells}) else 0
            if 100 < ex <= 1200 and sz is not None and int(sz.get('height') or 0) > 0: s.shrink_rows(cells, min(ex, 0.25 * max(rh.values())) / 100, last_only=True)
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
        sq = None
        if pos.get('treatAsChar') != '1' and tbl.get('textWrap') == 'SQUARE' and pos.get('horzAlign') in ('LEFT', 'RIGHT') and pos.get('horzRelTo') in ('COLUMN', 'PARA') and len(s.wstack) == 1 and 'margin-left:' not in ';'.join(st):
            sq = (pos.get('horzAlign'), int(pos.get('horzOffset') or 0) / 100, int(pos.get('vertOffset') or 0) / 100 if pos.get('vertRelTo') == 'PARA' else 0)      # 글 감싸기(네모): 표는 문단 맨 위에 떠 있고(자리 안 차지) 뒤따르는 문단의 줄이 저장된 시작 x 로 옆에 놓인다
        fo = None
        if pos.get('treatAsChar') != '1' and tbl.get('textWrap') == 'TOP_AND_BOTTOM' and pos.get('vertAlign') == 'BOTTOM' and pos.get('vertRelTo') in ('PAGE', 'PAPER') and s.page and len(s.wstack) == 1:
            fo = s.page_bottom_xy(pos, sum(colw) / 100, (int(sz.get('height')) + int(om.get('top')) + int(om.get('bottom'))) / 100)
            if fo: st.append('margin:0')
        out = [f'<table style="{";".join(st)}"{mark}><colgroup>' + ''.join(f'<col style="width:{pt(w)}">' for w in colw) + '</colgroup>']
        rows = {}
        for c in cells: rows.setdefault(c['r'], []).append(c)
        cellsplit = SPLIT_ON and tbl.get('pageBreak') == 'CELL'        # 셀 단위로 나뉘는 표만(HWP 는 표 속성 비트 0~1 = 2)
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
                cst = [f'width:{pt(c["w"])}', '' if (plan and STORED) or s.free_text(sub, c['h']) else f'height:{pt(c["h"])}',      # HTML 내보내기에선 높이를 남기고 hwp-nh 표시만
                       f'padding:{pt(mg.get("top"))} {pt(mg.get("right"))} {pt(mg.get("bottom"))} {pt(mg.get("left"))}',
                       'vertical-align:' + VALIGN.get(sub.get('vertAlign'), 'top')] + s.borders(bfid)
                f = s.fill(bfid); g = s.grad(s.bf.get(bfid))
                if f: cst.append(f'background-color:{f}')
                elif g: cst.append('background:' + g)      # 그라데이션 칸 배경(전엔 단색만 읽어 통째로 빠졌다)
                cst += s.fill_img(bfid)
                d = s.diagonal(bfid)
                if d: cst.append(d)
                span = (f' colspan="{c["cs"]}"' if c['cs'] > 1 else '') + (f' rowspan="{c["rs"]}"' if c['rs'] > 1 else '')
                ps = sub.findall(HP+'p')
                s.wstack.append(0 if sub.get('textDirection', 'HORIZONTAL') != 'HORIZONTAL' else max(c['w'] - int(mg.get('left') or 0) - int(mg.get('right') or 0), 0))      # 세로쓰기 칸은 줄 길이가 칸 높이 — 계산 안 함(CSS)
                try: inner = ''.join(s.paragraph(p, tuple(t for t, on in (('top', i == 0), ('bottom', i == len(ps) - 1)) if on)) for i, p in enumerate(ps))
                finally: s.wstack.pop()
                out.append(f'<td{span}{" class=\"hwp-nh\"" if plan and not STORED else ""} style="{";".join(x for x in cst if x)}">{inner}</td>')
            out.append('</tr>')
        if nh: out.append('</tbody>')
        out.append('</table>')
        cap = tbl.find(HP + 'caption'); csub = cap.find(HP + 'subList') if cap is not None else None
        if csub is not None:      # 표 캡션(hp:caption: 표 위·아래 글, 예: 추진일정 표 아래 ※ 주석 두 줄). 예전엔 통째로 빠졌다. 방향 TOP·LEFT 는 표 위, BOTTOM·RIGHT 는 표 아래(위·아래 캡션 폭 = 표 폭)
            tw = int(sz.get('width')) if sz is not None else 0
            s.wstack.append(tw or None)
            try: ctext = ''.join(s.paragraph(q) for q in csub.findall(HP + 'p'))
            finally: s.wstack.pop()
            if ctext:
                gap = int(cap.get('gap') or 0) / 100      # 표와 캡션 사이(HWPUNIT)
                above = cap.get('side') in ('TOP', 'LEFT')
                cdiv = f'<div style="{f"width:{pt(tw)};" if tw else ""}margin-{"bottom" if above else "top"}:{gap:g}pt">{ctext}</div>'
                return s.sq_wrap(s.fo_wrap((cdiv + ''.join(out)) if above else (''.join(out) + cdiv), fo), sq)
        return s.sq_wrap(s.fo_wrap(''.join(out), fo), sq)

def convert(src, dst):
    SKIPPED.clear(); PIDX[0] = 0; VZ[0] = VZ[1] = 0
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
    empty = lambda b: re.fullmatch(r'<p(?: data-\w+="[^"]*")* style="[^"]*"><br></p>', b) is not None
    keep = [not (empty(b) and i + 1 < len(blocks) and paras[i + 1].get('pageBreak') == '1') for i, b in enumerate(blocks)]
    i = len(blocks) - 1
    while i > 0 and empty(blocks[i]): keep[i] = False; i -= 1       # 끝의 빈 문단이 여러 개면 모두 (첫 문단은 남김)
    blocks = [b for b, k in zip(blocks, keep) if k]
    pg = cv.page
    if BODY_BOTTOM == 'pb' or BODY_BOTTOM == 'auto' and not cv.hf['footer']: pg = dict(pg, bottom=pg['bottom'] - pg['foot'])      # 꼬리말 높이를 본문에서 빼지 않는다(실험, hwp2html.BODY_BOTTOM)
    title = re.sub(r'<[^>]+>', '', blocks[0]) if blocks else 'document'
    # 머리글·바닥글: 홀수 쪽은 BOTH·ODD, 짝수 쪽은 BOTH·EVEN 중 처음 나온 것. 쪽 여백 상자의 running 요소로 쪽마다 되풀이한다(예전엔 첫 쪽 위·마지막 쪽 아래에 한 번만 나왔다)
    pick = lambda kind, ok: next((h for h in cv.hf[kind] if cv.hf_type[kind].get(h, 'BOTH') in ok), None)
    hd_o, hd_e, ft_o, ft_e = pick('header', ('BOTH', 'ODD')), pick('header', ('BOTH', 'EVEN')), pick('footer', ('BOTH', 'ODD')), pick('footer', ('BOTH', 'EVEN'))
    pagenum = pgn_css = ''; pn = cv.page_num
    if pn is not None and pn.get('pos', 'BOTTOM_CENTER') != 'NONE':        # pos="NONE" 은 쪽 번호를 안 찍는다(예전엔 그래도 찍었다)
        clean = lambda ch: ''.join(c for c in ch if c not in ('"', chr(92)))
        sc = clean(pn.get('sideChar', '')); fr, bk = (f'{sc} ', f' {sc}') if sc else ('', '')
        cnt = {'ROMAN_CAPITAL': 'upper-roman', 'ROMAN_SMALL': 'lower-roman', 'LATIN_CAPITAL': 'upper-alpha', 'LATIN_SMALL': 'lower-alpha'}.get(pn.get('formatType'), 'decimal')
        edge, side = {'TOP_LEFT': ('top', 'left'), 'TOP_CENTER': ('top', 'center'), 'TOP_RIGHT': ('top', 'right'), 'BOTTOM_LEFT': ('bottom', 'left'), 'BOTTOM_RIGHT': ('bottom', 'right')}.get(pn.get('pos'), ('bottom', 'center'))
        if (edge == 'bottom' and (ft_o or ft_e)) or (edge == 'top' and (hd_o or hd_e)):
            # 쪽 여백 상자는 머리글·바닥글 상자(폭 전체)와 같은 줄에서 자리가 없어 번호가 세로로 꺾인다 → 번호를 머리글·바닥글 안에 높이 0 으로 얹는다(PDF 에서만 보임)
            yy = max(0, pg['foot'] / 200 - 6) if edge == 'bottom' else 0
            pbox = f'<div class="hwp-pgn" style="position:relative;height:0"><div style="position:absolute;left:0;right:0;top:{yy:g}pt;text-align:{side};font-size:10pt">{html.escape(fr)}<span class="pgn"></span>{html.escape(bk)}</div></div>'
            if edge == 'bottom': ft_o, ft_e = (ft_o + pbox if ft_o else ft_o), (ft_e + pbox if ft_e else ft_e)
            else: hd_o, hd_e = (hd_o + pbox if hd_o else hd_o), (hd_e + pbox if hd_e else hd_e)
            pagenum = ''
            pgn_css = f'.pgn::before{{content:counter(page,{cnt})}}\n'
        else:
            pn_pos = ';vertical-align:bottom;padding-bottom:%gpt' % ((pg['bottom'] - pg['foot']) / 100 + 1.4) if edge == 'bottom' else ''      # 한컴은 쪽 번호 글자의 아래끝을 아래 여백 위 가장자리(용지 높이 - 아래 여백)에 둔다(우리 쪽 여백 상자는 글을 그 가장자리 아래에서 시작해 12pt 낮았다)
            pagenum = f' @{edge}-{side}{{content:"{fr}" counter(page,{cnt}) "{bk}";font-size:10pt{pn_pos}}}'
    same_h, same_f = hd_o == hd_e, ft_o == ft_e
    tw = pg['w'] - pg['left'] - pg['right']
    hbox = lambda nm, h, f: (f'@top-left{{content:element(hwphead{nm});width:{pt(tw)};vertical-align:top;padding-top:{pt(pg["mtop"])}}}' if h else '') + (f'@bottom-left{{content:element(hwpfoot{nm});width:{pt(tw)};vertical-align:top}}' if f else '')
    parity = '' if same_h and same_f else ''.join(f'@page:{sd}{{{hbox(t, None if same_h else h, None if same_f else f)}}}\n' for sd, t, h, f in (('right', 'o', hd_o, ft_o), ('left', 'e', hd_e, ft_e)))
    run = ''.join(f'.hwp-header{t}{{position:running(hwphead{t})}}\n' for t, h in ((('', hd_o),) if same_h else (('o', hd_o), ('e', hd_e))) if h)
    run += ''.join(f'.hwp-footer{t}{{position:running(hwpfoot{t})}}\n' for t, f in ((('', ft_o),) if same_f else (('o', ft_o), ('e', ft_e))) if f)
    run += pgn_css + '.hwp-run,.hwp-pgn{display:none}\n'
    mbox = hbox('', hd_o if same_h else None, ft_o if same_f else None)
    css = (f'@page{{size:{pt(pg["w"])} {pt(pg["h"])};margin:{pt(pg["top"])} {pt(pg["right"])} {pt(pg["bottom"])} {pt(pg["left"])};{pagenum}{mbox}}}\n{parity}{run}'
           'body{margin:0;background:#e9eaec;color:#000}\n'
           f'.page{{box-sizing:border-box;width:{pt(pg["w"])};min-height:{pt(pg["h"])};margin:24px auto;background:#fff;'
           f'padding:{pt(pg["top"])} {pt(pg["right"])} {pt(pg["bottom"])} {pt(pg["left"])};box-shadow:0 2px 10px rgba(0,0,0,.15)}}\n'
           'p,div{margin:0;orphans:1;widows:1}\np,div,td{white-space:pre-wrap;word-break:keep-all;overflow-wrap:break-word}\ntd>p,td>div{white-space:pre-wrap}\n'
           '.page{white-space:normal}\n'     # 문단 사이 줄바꿈 글자가 pre-wrap 에서 빈 줄 한 줄로 그려져 문단마다 14pt 가량 늘어나던 문제(쪽 수가 한컴의 2배가 되던 주원인)
           '.tb>p:last-child{margin-bottom:0!important}\n'      # 글상자 맨 아래 문단의 '문단 아래 간격'은 상자 높이에 안 더한다(상자 크기는 한컴이 저장한 curSz; pr-1674 '참고' 라벨 상자가 간격 10pt 만큼 커져 줄·표가 9pt 커졌다)
           'td{box-sizing:border-box}\n'      # 칸의 height 는 안쪽 여백까지 포함한 값(HWPX cellSz). 기본값(content-box)이면 칸마다 여백만큼 커져서 표가 세로로 길어진다
           '.mid{font-family:"바탕","Batang","Nanum Myeongjo",serif}\n'      # 가운뎃점 ㆍ(U+318D)을 바탕 글꼴로(hwp2html.mid_dot)
           '@media print{body{background:#fff}.page{box-shadow:none;margin:0;padding:0;width:auto;min-height:0}}')
    pbdiv = ''
    pb = getattr(cv, 'pbf', None)
    if pb:      # 쪽 테두리(pageBorderFill): 종이 기준이면 종이 가장자리에서 안쪽으로, 본문 기준이면 본문 가장자리에서 바깥쪽으로(hwp2html.master_layer 와 같음). 쪽마다 반복되는 고정 상자
        pw_, ph_, ml_, mt_ = pg['w'] / 100, pg['h'] / 100, pg['left'] / 100, pg['top'] / 100
        ol, orr, ot, ob = (v / 100 for v in pb['off'])
        x0, y0, x1, y1 = (ol, ot, pw_ - orr, ph_ - ob) if pb['paper'] else (ml_ - ol, mt_ - ot, pw_ - pg['right'] / 100 + orr, ph_ - pg['bottom'] / 100 + ob)
        box = lambda a, b, c, d, cls, extra: (f'<div class="{cls}{" mm" if (a < ml_ or b < mt_) and cls.startswith("mo") else ""}" style="--px:{a:g}pt;--py:{b:g}pt;--cx:{a - ml_:g}pt;--cy:{b - mt_:g}pt;width:{c - a:g}pt;height:{d - b:g}pt;box-sizing:border-box;' + extra + '"></div>' + chr(10))
        b_ = pb['bf']; fb = cv.bf.get(b_)
        fill = cv.fill_img(b_) or ([f'background:{cv.grad(fb)}'] if cv.grad(fb) else ([f'background:{cv.fill(b_)}'] if (cv.fill(b_) or '#ffffff').lower() != '#ffffff' else []))      # 쪽 채움: 그림 > 그라데이션 > 단색(HWP5-nopassword 는 가운데 놓인 큰 그림)
        vb, vf = pb['vis']      # 쪽 테두리·배경 보이기(hp:visibility border·fill): SHOW_FIRST = 첫 쪽만(HWP5-nopassword 의 큰 배경 그림은 첫 쪽에만 있다) → 쪽마다 되풀이하지 않고 첫 쪽에만 놓는 absolute(.fo), HIDE_ALL = 안 그림
        if fill and vf != 'HIDE_ALL':
            fx0, fy0, fx1, fy1 = {'PAPER': (0, 0, pw_, ph_), 'PAGE': (ml_, mt_, pw_ - pg['right'] / 100, ph_ - pg['bottom'] / 100)}.get(pb['area'], (x0, y0, x1, y1))
            pbdiv += box(fx0, fy0, fx1, fy1, 'fo bgf' if vf == 'SHOW_FIRST' else 'mo bgf', ';'.join(fill))
        if vb != 'HIDE_ALL' and any(not b.endswith(':none') for b in cv.borders(pb['bf'])): pbdiv += box(x0, y0, x1, y1, 'fo' if vb == 'SHOW_FIRST' else 'mo', ';'.join(cv.borders(pb['bf'])))
        if pbdiv: css += chr(10) + '@media print{.mo{position:fixed;left:var(--cx);top:var(--cy)} .mo.mm{display:none} .fo{position:absolute;left:var(--cx);top:var(--cy)} .bgf{z-index:-1} .page{background:transparent}}' + chr(10) + '@media screen{.page{position:relative;z-index:0} .mo,.fo{position:absolute;left:var(--px);top:var(--py)} .bgf{z-index:-1}}' + chr(10)
    if any('class="fo"' in b for b in blocks) and '.fo{' not in css:      # 쪽 기준으로 놓은 떠 있는 표(쪽 아래 정렬)
        css += chr(10) + '@media print{.fo{position:absolute;left:var(--cx);top:var(--cy)}}' + chr(10) + '@media screen{.page{position:relative} .fo{position:absolute;left:var(--px);top:var(--py)}}'
    n_body = len(blocks)
    hdv = [(('', hd_o),) if same_h else (('o', hd_o), ('e', hd_e))][0]
    fdv = [(('', ft_o),) if same_f else (('o', ft_o), ('e', ft_e))][0]
    # WeasyPrint 의 running 요소는 그 요소가 나온 쪽부터 쓸 수 있어, 본문 끝에만 있는 바닥글은 마지막 쪽에서만 보였다 → 본문 맨 앞에도 같은 바닥글을 둔다(브라우저에선 숨김, PDF 에서만 보임)
    blocks = [f'<div class="hwp-header{t}">{h}</div>' for t, h in hdv if h] + [f'<div class="hwp-footer{t} hwp-run">{f}</div>' for t, f in fdv if f] + blocks + [f'<div class="hwp-footer{t}">{f}</div>' for t, f in fdv if f]
    vz = '<meta name="hwp-vz" content="%.3f">' % (VZ[1] / VZ[0]) + chr(10) if STORED and VZ[0] >= 10 else ''
    if any(int(c.get('colCount') or 1) > 1 for sec in secs for c in sec.iter(HP+'colPr')): vz += '<meta name="hwp-multicol" content="1">' + chr(10)      # 다단 구역이 있는 문서(HWPX 경로는 다단을 못 그린다): 쪽 나눔 맞추기에서 뺀다(단이 바뀔 때도 저장 위치가 되돌아간다)
    doc = (f'<!DOCTYPE html>\n<html lang="ko"><head><meta charset="utf-8">\n{vz}<title>{html.escape(title.strip())}</title>\n'
           f'<style>\n{css}\n</style></head>\n<body><div class="page">\n' + pbdiv + '\n'.join(blocks) + '\n</div></body></html>\n')
    open(dst, 'w', encoding='utf-8').write(mid_dot(doc))
    if SKIPPED: print(f'경고: 읽을 수 없는 그림 {len(SKIPPED)}개를 뺐습니다 (벡터·깨진 그림: {", ".join(sorted(set(SKIPPED)))})', file=sys.stderr)
    return n_body

if __name__ == '__main__':
    print(convert(sys.argv[1], sys.argv[2]), 'top-level paragraphs')

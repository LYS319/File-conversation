"""hwpx2html.py 에 '저장된 줄이 없는 문단의 자연 줄 끊김'(core/natural.py)을 연결하는 일회용 패치(적용 뒤에는 이 파일 필요 없음). 사용: python devtools/patch_hwpx_natural.py"""
import sys
from pathlib import Path

P = Path(__file__).resolve().parents[1] / 'hwpx2html.py'
s = P.read_text(encoding='utf-8')


def sub(a, b, count=1):
    global s
    assert a in s, a[:70]
    s = s.replace(a, b, count)


# 1) 설정과 import
sub("_SL = os.environ.get('STORED_LAYOUT', '')",
    "from core import natural as _natural      # V3 1단계: 저장된 줄이 없는 문단의 줄 끊김을 우리가 계산한다(core/natural.py)\n"
    "NATURAL = os.environ.get('NATURAL_BREAKS', 'on') != 'off'      # off 면 CSS 줄 나눔(V2 와 같은 동작)\n"
    "IGNORE_LINESEG = os.environ.get('IGNORE_LINESEG') == '1'      # 시험용: 저장된 줄(linesegarray)을 무시한다\n"
    "LANG_KEYS = (('hangul', 'HANGUL'), ('latin', 'LATIN'), ('hanja', 'HANJA'), ('japanese', 'JAPANESE'), ('other', 'OTHER'), ('symbol', 'SYMBOL'), ('user', 'USER'))\n"
    "_SL = os.environ.get('STORED_LAYOUT', '')")

# 2) Conv: 폭 스택·글자 모양 어댑터·자연 줄 끊김
sub("        s.cp = {c.get('id'): c for c in head.iter(HH+'charPr')}",
    "        s.cp = {c.get('id'): c for c in head.iter(HH+'charPr')}\n"
    "        s.wstack = [None]      # 문단이 놓인 칸의 글 폭(HWPUNIT). None = 본문 폭, 0 = 모름(자연 줄 끊김 계산 안 함)\n"
    "        s._cs = {}; s.page = None")
sub("    def section(s, sec):",
    '''    def body_w(s):
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
                    if t2 == 'fwSpace': add('\\u2007', cid)
                    elif t2 == 'nbSpace': add('\\u00a0', cid)
                    elif t2 == 'hyphen': add('-', cid)
                    else: return None      # lineBreak·tab 등: CSS 에 맡김
                    add(sub_.tail or '', cid)
        if not chars: return None
        case = pp.find(f'{HP}switch/{HP}case'); box = case if case is not None else pp
        mg = box.find(HH+'margin')
        if mg is None: return None
        left, right, ind = (int(mg.find(HC+n).get('value')) for n in ('left', 'right', 'intent'))
        bs = pp.find(HH+'breakSetting'); ku = bs is not None and bs.get('breakNonLatinWord') == 'KEEP_WORD'      # 한컴: KEEP_WORD = 글자 단위
        return _natural.natural_breaks(chars, lambda q: s.charstyle(cids[q]), ku, ind * 2, w - left - right, prefix=prefix) or None

    def section(s, sec):''')

# 3) paragraph(): 저장된 줄이 없으면 자연 줄 끊김
sub("""            if sg0 is not None and len(sg0) and all(int(l.get('vertsize') or 0) > 0 for l in sg0) and not any(True for _ in p.iter(HP+'tbl', HP+'pic', HP+'rect', HP+'chart', HP+'lineBreak', HP+'tab')):
                if len(sg0) == 1: single = True
                else: brk = {'pos': 0, 'set': {int(l.get('textpos')) for l in sg0[1:]}}""",
    """            prefix = s.number_prefix(p.get('paraPrIDRef'))      # 번호 카운터가 늘어나는 부작용이 있어 한 번만 부른다(자연 줄 끊김이 접두 폭을 알려고 먼저 필요)
            simple = not any(True for _ in p.iter(HP+'tbl', HP+'pic', HP+'rect', HP+'chart', HP+'lineBreak', HP+'tab'))
            if sg0 is not None and len(sg0) and all(int(l.get('vertsize') or 0) > 0 for l in sg0) and simple and not IGNORE_LINESEG:
                if len(sg0) == 1: single = True
                else: brk = {'pos': 0, 'set': {int(l.get('textpos')) for l in sg0[1:]}}
            elif NATURAL and simple:
                sp_ = p.find('.//' + HP + 'secPr')
                if sp_ is not None and s.page is None: s.section(sp_)      # 구역 첫 문단: 쪽 폭을 먼저 알아야 한다
                nb = s.natural_brk(p, runs, prefix)
                if nb: brk = {'pos': 0, 'set': nb}""")

sub("        prefix = s.number_prefix(p.get('paraPrIDRef'))\n        if prefix and first_cid:", "        if prefix and first_cid:")      # 번호 접두는 위에서 먼저 계산했다

# 4) 표 칸: 칸 폭 - 안쪽 여백
sub("""                inner = ''.join(s.paragraph(p, tuple(t for t, on in (('top', i == 0), ('bottom', i == len(ps) - 1)) if on)) for i, p in enumerate(ps))""",
    """                s.wstack.append(max(c['w'] - int(mg.get('left') or 0) - int(mg.get('right') or 0), 0))
                try: inner = ''.join(s.paragraph(p, tuple(t for t, on in (('top', i == 0), ('bottom', i == len(ps) - 1)) if on)) for i, p in enumerate(ps))
                finally: s.wstack.pop()""")

# 5) 글상자: 개체 폭 - 글상자 안쪽 여백
sub("""                        parts.append('<div style="display:inline-block;vertical-align:top">' + ''.join(s.paragraph(q) for q in sub.findall(HP+'p')) + '</div>')""",
    """                        szr = ch.find(HP+'sz'); tm = dt.find(HP+'textMargin')
                        s.wstack.append(max(int(szr.get('width')) - int(tm.get('left') or 0) - int(tm.get('right') or 0), 0) if szr is not None and tm is not None else 0)
                        try: parts.append('<div style="display:inline-block;vertical-align:top">' + ''.join(s.paragraph(q) for q in sub.findall(HP+'p')) + '</div>')
                        finally: s.wstack.pop()""")

# 6) 머리말·꼬리말: 본문 폭
sub("""                            h = ''.join(s.paragraph(q) for q in sub.findall(HP+'p'))""",
    """                            s.wstack.append(None)      # 머리말·꼬리말 글 폭 = 본문 폭
                            try: h = ''.join(s.paragraph(q) for q in sub.findall(HP+'p'))
                            finally: s.wstack.pop()""")
P.write_text(s, encoding='utf-8')
print('패치 적용 완료')

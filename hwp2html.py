"""HWP 5.0(.hwp, OLE2) -> 단일 HTML. 사진은 JPEG data URI로 넣는다.
claude.ai 채팅의 Claude가 샌드박스에서 즉석으로 짠 파서(cfb.py + convert.py + 번호/글머리/들여쓰기 패치)를 그대로 복원한 것.
# ponytail: 그 문서 한 건에 맞춘 프로토타입. 구역은 Section0만, 표 테두리·폭 단순화, span에 글꼴 없음, 쪽 설정·머리글·바닥글 없음.
#           보강은 일반화 시험(근무계획서 .hwp)에서 나온 차이 목록 순서로 한다.
#           모듈 전역 상태를 쓰므로 프로세스당 변환 1건씩 호출하는 것을 전제로 한다(convert()는 호출마다 상태를 다시 읽음)."""
import base64, html, io, re, struct, sys, zlib
from pathlib import Path
from PIL import Image

MAX_BYTES = 100 * 1024 * 1024            # 회의록 66MB를 받아들이는 상한 (계획서 8장 입력 방어)
MAX_STREAM = 512 * 1024 * 1024           # 스트림 하나를 푼 크기 상한. 회의록의 BMP 사진은 장당 70MB라 100MB로 잡으면 정상 문서가 막힌다


class CFB:
    """OLE2 복합 파일 리더 (olefile 없이)"""
    def __init__(self, path):
        self.d = Path(path).read_bytes()
        d = self.d
        if d[:8] != bytes.fromhex('D0CF11E0A1B11AE1'): raise ValueError('OLE2 파일이 아님')
        self.ss = 1 << struct.unpack_from('<H', d, 30)[0]
        self.mss = 1 << struct.unpack_from('<H', d, 32)[0]
        nfat, = struct.unpack_from('<I', d, 44)
        firstdir, = struct.unpack_from('<I', d, 48)
        self.cutoff, = struct.unpack_from('<I', d, 56)
        fminifat, nminifat, fdifat, ndifat = struct.unpack_from('<IIII', d, 60)
        difat = list(struct.unpack_from('<109I', d, 76))
        s = fdifat
        while s not in (0xFFFFFFFE, 0xFFFFFFFF) and ndifat:
            sec = self.sec(s); n = self.ss // 4
            v = struct.unpack('<%dI' % n, sec); difat += v[:-1]; s = v[-1]; ndifat -= 1
        difat = [x for x in difat if x < 0xFFFFFFFA][:nfat]
        fat = b''.join(self.sec(x) for x in difat)
        self.fat = struct.unpack('<%dI' % (len(fat) // 4), fat)
        dirdata = self.chain(firstdir)
        self.entries = []
        for i in range(len(dirdata) // 128):
            e = dirdata[i * 128:(i + 1) * 128]
            nl, = struct.unpack_from('<H', e, 64)
            name = e[:max(nl - 2, 0)].decode('utf-16le')
            typ = e[66]; l, r, c = struct.unpack_from('<III', e, 68)
            start, = struct.unpack_from('<I', e, 116); size, = struct.unpack_from('<Q', e, 120)
            if self.ss == 512: size &= 0xFFFFFFFF
            self.entries.append(dict(name=name, type=typ, left=l, right=r, child=c, start=start, size=size))
        root = self.entries[0]
        self.ministream = self.chain(root['start'])[:root['size']] if root['start'] < 0xFFFFFFFA else b''
        mf = self.chain(fminifat) if nminifat else b''
        self.minifat = struct.unpack('<%dI' % (len(mf) // 4), mf)
        self.paths = {}
        self._walk(root['child'], '', set())

    def sec(self, i): o = (i + 1) * self.ss; return self.d[o:o + self.ss]

    def chain(self, s):
        out = []
        for _ in range(len(self.fat) + 1):                   # FAT 순환(손상·악의 파일) 방어
            if s >= 0xFFFFFFFA: return b''.join(out)
            out.append(self.sec(s)); s = self.fat[s]
        raise ValueError('FAT 순환')

    def _walk(self, i, prefix, seen):
        if i >= len(self.entries) or i in seen: return
        seen.add(i)
        e = self.entries[i]
        self._walk(e['left'], prefix, seen); self._walk(e['right'], prefix, seen)
        p = prefix + '/' + e['name']; self.paths[p] = i
        if e['type'] in (1, 5): self._walk(e['child'], p, seen)

    def read(self, p):
        e = self.entries[self.paths[p]]
        if e['size'] < self.cutoff:
            out = []; s = e['start']
            for _ in range(len(self.minifat) + 1):
                if s >= 0xFFFFFFFA: break
                o = s * self.mss; out.append(self.ministream[o:o + self.mss]); s = self.minifat[s]
            return b''.join(out)[:e['size']]
        return self.chain(e['start'])[:e['size']]


# ---- 문서 상태 (load()가 채운다)
c = COMP = nhangul = None
faces = []; bins = []; borderfills = []; charshapes = []; parashapes = []; numberings = []
NUMC = {}
IMAGES = []


def dec(b, force=None):
    if force is False or not (COMP if force is None else force): return b
    d = zlib.decompressobj(-15); out = d.decompress(b, MAX_STREAM + 1)      # 압축 폭탄 방어: 푼 크기가 상한을 넘으면 거부
    if len(out) > MAX_STREAM: raise ValueError('압축을 푼 크기가 한도(스트림당 512MB)를 넘음')
    if not d.eof: raise zlib.error('incomplete or truncated stream')       # zlib.decompress와 같은 동작 유지
    return out


def records(b):
    i = 0; out = []
    while i < len(b):
        h, = struct.unpack_from('<I', b, i); i += 4
        tag = h & 0x3FF; lvl = (h >> 10) & 0x3FF; sz = h >> 20
        if sz == 0xFFF: sz, = struct.unpack_from('<I', b, i); i += 4
        out.append((tag, lvl, b[i:i + sz])); i += sz
    return out


def load(src):
    """DocInfo(글꼴·글자/문단 모양·테두리/배경·번호매기기·BinData)를 읽는다"""
    global c, COMP, nhangul
    if Path(src).stat().st_size > MAX_BYTES: raise ValueError('파일이 너무 큼 (상한 100MB)')
    c = CFB(src)
    fh = c.read('/FileHeader')
    if fh[:17] != b'HWP Document File': raise ValueError('HWP 5.0 파일이 아님')
    flags, = struct.unpack_from('<I', fh, 36)
    if flags & 0b10110: raise ValueError('암호화/배포용/DRM 문서는 지원하지 않음')      # bit1 암호, bit2 배포용, bit4 DRM
    COMP = flags & 1
    for L in (faces, bins, borderfills, charshapes, parashapes, numberings, IMAGES): L.clear()
    NUMC.clear()
    di = records(dec(c.read('/DocInfo')))
    idmap = next(p for t, _, p in di if t == 17)
    _, nhangul = struct.unpack_from('<II', idmap, 0)
    for t, l, p in di:
        if t == 19:
            n, = struct.unpack_from('<H', p, 1); faces.append(p[3:3 + 2 * n].decode('utf-16le'))
        elif t == 18:
            prop, bid, n = struct.unpack_from('<HHH', p, 0); ext = p[6:6 + 2 * n].decode('utf-16le')
            bins.append(dict(id=bid, ext=ext, comp=(prop >> 4) & 3))
        elif t == 20:
            fill = None
            ft, = struct.unpack_from('<I', p, 32)
            if ft & 1 and len(p) >= 40:
                col, = struct.unpack_from('<I', p, 36)
                if col != 0xFFFFFFFF: fill = col
            borders = [p[6 * k] for k in range(4)]  # line type per side (현재 사용 안 함)
            borderfills.append(dict(fill=fill, borders=borders))
        elif t == 21:
            face0, = struct.unpack_from('<H', p, 0)
            size, prop = struct.unpack_from('<iI', p, 42)
            color, = struct.unpack_from('<I', p, 52)
            charshapes.append(dict(face=faces[face0] if face0 < nhangul and face0 < len(faces) else None,
                size=size / 100, bold=bool(prop & 2), italic=bool(prop & 1), underline=(prop >> 2) & 3, color=color, strike=bool((prop >> 18) & 7)))
        elif t == 23:
            q = 0; levels = []
            for lv in range(7):
                pr, = struct.unpack_from('<I', p, q); q += 12
                n, = struct.unpack_from('<H', p, q); q += 2
                levels.append(dict(fmt=p[q:q + 2 * n].decode('utf-16le'), shape=(pr >> 5) & 0xF)); q += 2 * n
            numberings.append(levels)
        elif t == 25:
            prop, = struct.unpack_from('<I', p, 0)
            left, right, indent, top, bottom, ls = struct.unpack_from('<iiiiii', p, 4)
            parashapes.append(dict(head=(prop >> 23) & 3, level=(prop >> 25) & 7, numid=struct.unpack_from('<H', p, 30)[0],
                align=(prop >> 2) & 7, left=left, right=right, indent=indent, top=top, bottom=bottom, ls=ls, lstype=prop & 3))


def rgb(v): return '#%02x%02x%02x' % (v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF)


def bindata_uri(bid):
    b = next(x for x in bins if x['id'] == bid)
    raw = c.read('/BinData/BIN%04X.%s' % (bid, b['ext']))
    data = dec(raw, None if b['comp'] == 0 else (b['comp'] == 1))
    im = Image.open(io.BytesIO(data)).convert('RGB')
    IMAGES.append((bid, im.size))
    im.thumbnail((1400, 1400))
    buf = io.BytesIO(); im.save(buf, 'JPEG', quality=85, optimize=True)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()


# ---- 본문 텍스트
EXT = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}; INL = {4, 5, 6, 7, 8, 9, 19, 20}
PUA = {0xF09F: '•', 0xF09E: '·', 0xF0A7: '▪', 0xF0A0: '▪', 0xF0D8: '➢', 0xF0FC: '✔', 0xF0B7: '•',
       0xF0854: '『', 0xF0855: '』', 0xF0039: '⬅', 0xF003B: '⬇'}      # 뒤 4개: HWPX 의 보조 평면 사설 문자. 공고문을 한컴 렌더로 그려 모양을 확인했다(HWP 는 UTF-16 조각 단위라 여기서 걸리지 않는다)


def para_text(b):
    s = struct.unpack('<%dH' % (len(b) // 2), b); i = 0; out = []
    while i < len(s):
        ch = s[i]
        if ch < 32:
            if ch in EXT or ch in INL:
                if ch == 9: out.append((i, '\t'))
                elif ch in EXT: out.append((i, ('CTRL', bytes(b[2 * i + 2:2 * i + 6])[::-1].decode('latin1'))))
                i += 8; continue
            if ch == 10: out.append((i, '\n'))
            elif ch in (24,): out.append((i, '-'))
            elif ch in (30, 31): out.append((i, ' '))
            i += 1; continue
        out.append((i, PUA.get(ch, chr(ch)))); i += 1
    return out


ALIGN = {0: 'justify', 1: 'left', 2: 'right', 3: 'center', 4: 'justify', 5: 'justify'}


def hu(v): return v / 75  # HWPUNIT -> px (7200/inch, 96dpi)


def span_style(cs):
    st = ['font-size:%gpt' % cs['size']]
    if cs['bold']: st.append('font-weight:700')
    if cs['italic']: st.append('font-style:italic')
    if cs['underline'] == 1: st.append('text-decoration:underline')
    if cs['strike']: st.append('text-decoration:line-through')
    if cs['color'] & 0xFFFFFF: st.append('color:' + rgb(cs['color']))
    return ';'.join(st)


class Node:
    def __init__(s, tag, lvl, p): s.tag, s.lvl, s.p, s.ch = tag, lvl, p, []


def tree(recs):
    root = Node(-1, -1, b''); stack = [root]
    for t, l, p in recs:
        n = Node(t, l, p)
        while stack[-1].lvl >= l: stack.pop()
        stack[-1].ch.append(n); stack.append(n)
    return root


def render_para(n):
    ps = parashapes[struct.unpack_from('<H', n.p, 8)[0]]
    text = []; csr = []
    for ch in n.ch:
        if ch.tag == 67: text = para_text(ch.p)
        elif ch.tag == 68: csr = [struct.unpack_from('<II', ch.p, 8 * k) for k in range(len(ch.p) // 8)]
    ctrls = [ch for ch in n.ch if ch.tag == 71]
    ci = 0; inner = []; cur = None; buf = ''

    def csat(pos):
        r = csr[0][1]
        for a, bb in csr:
            if a <= pos: r = bb
        return r

    def flush():
        nonlocal buf
        if buf:
            inner.append('<span style="%s">%s</span>' % (span_style(charshapes[cur]), html.escape(buf).replace('\n', '<br>').replace('\t', '&emsp;')))
            buf = ''
    blocks = []
    for pos, v in text:
        if isinstance(v, tuple):
            while ci < len(ctrls) and ctrls[ci].p[:4][::-1].decode('latin1') != v[1]: ci += 1
            if ci < len(ctrls):
                ctl = ctrls[ci]; ci += 1
                if v[1] == 'tbl ': flush(); blocks.append(('inl', render_table(ctl)))
                elif v[1] == 'gso ': flush(); blocks.append(('inl', render_gso(ctl)))
            continue
        k = csat(pos)
        if k != cur: flush(); cur = k
        buf += v
    flush()
    prefix = ''
    if ps['head'] == 2 and 0 < ps['numid'] <= len(numberings) and text:
        key = (ps['numid'], ps['level']); NUMC[key] = NUMC.get(key, 0) + 1
        for k in list(NUMC):
            if k[0] == ps['numid'] and k[1] > ps['level']: del NUMC[k]
        fmt = numberings[ps['numid'] - 1][ps['level']]['fmt']
        prefix = re.sub(r'\^(\d)', lambda m: str(NUMC.get((ps['numid'], int(m.group(1)) - 1), 1)), fmt) + ' '
    if prefix: inner.insert(0, '<span style="%s">%s</span>' % (span_style(charshapes[csat(0)]), html.escape(prefix)))
    st = ['text-align:' + ALIGN.get(ps['align'], 'left')]
    ind = ps['indent'] / 2; left = ps['left'] / 2
    if ind < 0: st.append('padding-left:%.1fpx' % hu(left - ind)); st.append('text-indent:%.1fpx' % hu(ind))
    else:
        if left: st.append('padding-left:%.1fpx' % hu(left))
        if ind: st.append('text-indent:%.1fpx' % hu(ind))
    if ps['top']: st.append('margin-top:%.1fpx' % hu(ps['top'] / 2))
    if ps['bottom']: st.append('margin-bottom:%.1fpx' % hu(ps['bottom'] / 2))
    if ps['lstype'] == 0 and ps['ls']: st.append('line-height:%.2f' % (ps['ls'] / 100 * 0.85))
    body = ''.join(inner)
    out = ''
    if body or not blocks:
        out = '<p style="%s">%s</p>' % (';'.join(st), body or '&nbsp;')
    for _, bl in blocks: out += bl
    return out


def render_paras(nodes): return '\n'.join(render_para(n) for n in nodes if n.tag == 66)


def render_table(ctl):
    tbl = next(ch for ch in ctl.ch if ch.tag == 77)
    rows, cols = struct.unpack_from('<HH', tbl.p, 4)
    cells = []; kids = ctl.ch
    for idx, ch in enumerate(kids):
        if ch.tag == 72:
            col, row, cs, rs, w, h = struct.unpack_from('<HHHHII', ch.p, 8)
            bf, = struct.unpack_from('<H', ch.p, 32)
            vflag, = struct.unpack_from('<I', ch.p, 4)
            paras = []; j = idx + 1
            while j < len(kids) and kids[j].tag == 66: paras.append(kids[j]); j += 1
            paras += [x for x in ch.ch if x.tag == 66]
            cells.append(dict(row=row, col=col, cs=cs, rs=rs, w=w, bf=bf, valign=(vflag >> 21) & 3, paras=paras))
    tot = sum(x['w'] for x in cells if x['row'] == 0) or 1
    out = ['<table class="hwp-table">']
    for r in range(rows):
        out.append('<tr>')
        for cell in [x for x in cells if x['row'] == r]:
            st = ['width:%.1f%%' % (cell['w'] / tot * 100)]
            bfd = borderfills[cell['bf'] - 1] if 0 < cell['bf'] <= len(borderfills) else None
            if bfd and bfd['fill'] is not None and bfd['fill'] & 0xFFFFFF != 0xFFFFFF: st.append('background:' + rgb(bfd['fill']))
            st.append('vertical-align:' + ['top', 'middle', 'bottom'][min(cell['valign'], 2)])
            span = (' colspan="%d"' % cell['cs'] if cell['cs'] > 1 else '') + (' rowspan="%d"' % cell['rs'] if cell['rs'] > 1 else '')
            out.append('<td%s style="%s">%s</td>' % (span, ';'.join(st), render_paras(cell['paras'])))
        out.append('</tr>')
    out.append('</table>')
    return '\n'.join(out)


def find(n, tag):
    if n.tag == tag: return n
    for ch in n.ch:
        r = find(ch, tag)
        if r: return r


def render_gso(ctl):
    pic = find(ctl, 85)
    if not pic: return ''
    bid, = struct.unpack_from('<H', pic.p, 71)
    return '<figure><img src="%s" alt="첨부 이미지 %d"></figure>' % (bindata_uri(bid), bid)


def convert(src, dst):
    load(src)
    root = tree(records(dec(c.read('/BodyText/Section0'))))
    body = render_paras(root.ch)
    first = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', body.split('</p>')[0]))).strip()
    title = html.escape(first or Path(src).stem)
    page = f'''<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body{{margin:0;background:#e9eaec;font-family:"함초롬바탕","HCR Batang","Batang","Noto Serif KR","Malgun Gothic",serif;color:#000}}
.page{{max-width:794px;margin:24px auto;background:#fff;padding:56px 64px;box-shadow:0 2px 10px rgba(0,0,0,.15);box-sizing:border-box}}
p{{margin:0;white-space:pre-wrap;word-break:keep-all}}
.hwp-table{{width:100%;border-collapse:collapse;margin:6px 0;table-layout:fixed}}
.hwp-table td{{border:1px solid #000;padding:5px 8px;word-break:keep-all}}
figure{{margin:4px 0;text-align:center}} figure img{{max-width:100%;height:auto}}
@media print{{body{{background:#fff}}.page{{box-shadow:none;margin:0;max-width:none}}}}
@media (max-width:600px){{.page{{padding:24px 16px;margin:0}}}}
</style></head>
<body><div class="page">
{body}
</div></body></html>'''
    Path(dst).write_text(page, encoding='utf-8')
    return dict(bytes=len(page), images=[s for _, s in IMAGES], tables=body.count('<table'), fonts=sorted({cs['face'] for cs in charshapes if cs['face']}))


if __name__ == '__main__':
    print(convert(sys.argv[1], sys.argv[2]))

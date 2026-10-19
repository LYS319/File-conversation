"""이 PC 에 설치된 글꼴 파일에서 글자 폭(advance)을 직접 읽어 우리 폭표 `core/data/font_metrics_local.json.gz` 를 만든다.
rhwp 폭표(`rhwp_font_metrics.json.gz`, MIT)와 같은 모양이라 `core/metrics.py` 가 우리 표를 먼저, 없는 글꼴만 rhwp 표를 쓴다.
    python devtools/build_font_metrics.py [--check]     (--check: 파일을 쓰지 않고 rhwp 표와 비교만)
TrueType/OpenType(.ttf .otf .ttc)만 읽는다(표준 sfnt 구조: head·maxp·hhea·hmtx·cmap·name — 외부 패키지 없이 struct 로).
글꼴 파일은 저장소·이미지에 넣지 않는다. 읽는 것은 글자 폭 숫자뿐이다(THIRD_PARTY_NOTICES.md 6절)."""
import glob, gzip, json, os, struct, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[0]
OUT = HERE.parent / 'core' / 'data' / 'font_metrics_local.json.gz'
RHWP = HERE.parent / 'core' / 'data' / 'rhwp_font_metrics.json.gz'
DIRS = [os.environ.get('WINDIR', 'C:/Windows') + '/Fonts', os.path.expanduser('~/AppData/Local/Microsoft/Windows/Fonts')]
LATIN_RANGES = [(32, 126), (160, 255), (0x2000, 0x206F), (0x2200, 0x22FF), (0x3000, 0x303F), (0x3130, 0x318F), (0xFF00, 0xFF5E)]      # rhwp 폭표와 같은 범위(비교용)


class Face:
    """sfnt 글꼴 하나(TTC 면 면 하나). 필요한 표만 읽는다."""
    def __init__(s, data, off):
        s.d = data; s.tables = {}
        n = struct.unpack_from('>H', data, off + 4)[0]
        for i in range(n):
            tag, _, o, ln = struct.unpack_from('>4sIII', data, off + 12 + 16 * i)
            s.tables[tag.decode('latin1')] = (o, ln)
        s.em = struct.unpack_from('>H', data, s.tables['head'][0] + 18)[0]
        s.mac = struct.unpack_from('>H', data, s.tables['head'][0] + 44)[0]      # macStyle: 비트0 굵게, 비트1 기울임
        s.nglyph = struct.unpack_from('>H', data, s.tables['maxp'][0] + 4)[0]
        s.nhm = struct.unpack_from('>H', data, s.tables['hhea'][0] + 34)[0]
        s.cmap = None; s.names = None

    def advance_gid(s, g):
        o = s.tables['hmtx'][0]
        if g >= s.nhm: g = s.nhm - 1
        return struct.unpack_from('>H', s.d, o + 4 * g)[0]

    def load_cmap(s):
        if s.cmap is not None: return s.cmap
        o, ln = s.tables['cmap']; d = s.d; n = struct.unpack_from('>H', d, o + 2)[0]; subs = []
        for i in range(n):
            pid, eid, so = struct.unpack_from('>HHI', d, o + 4 + 8 * i); subs.append((pid, eid, o + so))
        best = None
        for pid, eid, so in subs:      # 유니코드 전체(3,10 · 0,4+) > BMP(3,1 · 0,3)
            fmt = struct.unpack_from('>H', d, so)[0]
            if fmt == 12 and (best is None or best[0] < 2): best = (2, so, fmt)
            elif fmt == 4 and (pid, eid) in ((3, 1), (0, 3), (0, 4), (0, 2), (0, 1), (0, 0)) and (best is None or best[0] < 1): best = (1, so, fmt)
        m = {}
        if best:
            so, fmt = best[1], best[2]
            if fmt == 4:
                segx2 = struct.unpack_from('>H', d, so + 6)[0]; seg = segx2 // 2; p = so + 14
                ends = struct.unpack_from('>%dH' % seg, d, p); p += 2 * seg + 2
                starts = struct.unpack_from('>%dH' % seg, d, p); p += 2 * seg
                deltas = struct.unpack_from('>%dh' % seg, d, p); p += 2 * seg
                rop = p; ros = struct.unpack_from('>%dH' % seg, d, p)
                for i in range(seg):
                    for c in range(starts[i], ends[i] + 1):
                        if c == 0xFFFF: continue
                        if ros[i] == 0: g = (c + deltas[i]) & 0xFFFF
                        else:
                            q = rop + 2 * i + ros[i] + 2 * (c - starts[i])
                            if q + 2 > len(d): continue
                            g = struct.unpack_from('>H', d, q)[0]
                            if g: g = (g + deltas[i]) & 0xFFFF
                        if g: m[c] = g
            else:
                ng = struct.unpack_from('>I', d, so + 12)[0]
                for i in range(ng):
                    sc, ec, sg = struct.unpack_from('>III', d, so + 16 + 12 * i)
                    for c in range(sc, ec + 1): m[c] = sg + c - sc
        s.cmap = m; return m

    def load_names(s):
        if s.names is not None: return s.names
        out = {}
        if 'name' in s.tables:
            o, ln = s.tables['name']; d = s.d; cnt, so = struct.unpack_from('>HH', d, o + 2)
            for i in range(cnt):
                pid, eid, lid, nid, l, off = struct.unpack_from('>6H', d, o + 6 + 12 * i)
                raw = d[o + so + off: o + so + off + l]
                try: txt = raw.decode('utf-16-be') if pid in (0, 3) else raw.decode('latin1')
                except Exception: continue
                out.setdefault(nid, []).append(txt)
        s.names = out; return out

    def keys(s):
        """이 면이 어떤 이름으로 불릴 수 있나(소문자·공백/하이픈 제거): 패밀리(1·16)·전체 이름(4)·PostScript(6)."""
        n = s.load_names(); ks = set()
        for nid in (1, 16, 4, 6):
            for t in n.get(nid, []): ks.add(norm(t))
        return ks


def norm(t): return ''.join(ch for ch in t.lower() if ch.isalnum())


def style_words(bold, italic): return 'Bold Italic' if bold and italic else 'Bold' if bold else 'Italic' if italic else 'Regular'


def matches(fc, name, bold, italic):
    """면 fc 가 (name, 굵기, 기울임) 항목인가. 전체 이름(4)이 '이름'(보통체) 또는 '이름 Bold/Italic/Bold Italic' 과 같고 macStyle 굵기·기울임도 맞을 때만.
    패밀리만 보면 Arial Narrow(패밀리 'Arial')·Leelawadee UI Semilight 같은 것을 잘못 고른다. 가변 글꼴(fvar)은 기본 인스턴스 폭이라 제외한다. 전체 이름이 없으면 패밀리+서브패밀리."""
    if 'fvar' in fc.tables or (bool(fc.mac & 1), bool(fc.mac & 2)) != (bool(bold), bool(italic)): return False
    n = fc.load_names(); want = norm(name); st = norm(style_words(bold, italic))
    full = {norm(t) for t in n.get(4, [])}
    if full: return bool(full & ({want, want + 'regular'} if st == 'regular' else {want + st}))
    fam = {norm(t) for i in (1, 16) for t in n.get(i, [])}; sub = {norm(t) for i in (2, 17) for t in n.get(i, [])}
    return want in fam and (st in sub or (st == 'regular' and (not sub or sub & {'regular', 'standard', 'normal', 'book', 'roman'})))


def faces():
    out = []
    for dd in DIRS:
        for f in sorted(glob.glob(dd + '/*')):
            if not f.lower().endswith(('.ttf', '.otf', '.ttc')): continue
            try: data = open(f, 'rb').read()
            except Exception: continue
            try:
                if data[:4] == b'ttcf':
                    n = struct.unpack_from('>I', data, 8)[0]
                    for i in range(n): out.append((f, Face(data, struct.unpack_from('>I', data, 12 + 4 * i)[0])))
                else: out.append((f, Face(data, 0)))
            except Exception: continue
    return out


def hangul_entry(face, em):
    cm = face.load_cmap(); ws = [face.advance_gid(cm[c]) if c in cm else None for c in range(0xAC00, 0xD7A4)]
    if any(w is None for w in ws): return None      # 가~힣 중 없는 글자가 있으면 이 면은 한글 폭을 못 준다
    u = set(ws)
    if len(u) == 1: return dict(cho_groups=1, jung_groups=1, jong_groups=1, cho_map=[0] * 19, jung_map=[0] * 21, jong_map=[0] * 28, widths=[ws[0]])
    # 글자마다 다르면 초·중·종성 색인 그대로(19×21×28 = 11172) 둔다 — rhwp 표 모양(hangul_width)과 같게
    return dict(cho_groups=19, jung_groups=21, jong_groups=28, cho_map=list(range(19)), jung_map=list(range(21)), jong_map=list(range(28)), widths=ws)


def latin_entry(face):
    cm = face.load_cmap(); out = []
    for s_, e_ in LATIN_RANGES:
        ws = [face.advance_gid(cm[c]) if c in cm else 0 for c in range(s_, e_ + 1)]
        if any(ws): out.append([s_, e_, ws])
    return out


def main(check):
    rh = json.load(gzip.open(RHWP, 'rt', encoding='utf-8'))
    fs = faces(); print('이 PC 글꼴 면 %d개' % len(fs))
    by_key = {}
    for f, fc in fs:
        for k in fc.keys(): by_key.setdefault(k, []).append((f, fc))
    all_faces = [fc for f, fc in fs]
    out, same, diff, miss = [], 0, [], []
    for e in rh['fonts']:
        pick = next((fc for f, fc in by_key.get(norm(e['name']), []) if matches(fc, e['name'], e['bold'], e['italic'])), None)
        if pick is None: miss.append((e['name'], e['bold'], e['italic'])); continue
        sc = e['em'] / pick.em
        lat = latin_entry(pick); hg = hangul_entry(pick, pick.em)
        # rhwp 항목과 비교: 같은 글자 폭이 얼마나 다른가
        cm = pick.load_cmap(); bad = 0; n = 0
        for s_, e_, ws in e['latin']:
            for c, w in zip(range(s_, e_ + 1), ws):
                if c in cm and w:
                    n += 1
                    if abs(pick.advance_gid(cm[c]) * sc - w) > 1.5: bad += 1
        if hg and e['hangul'] and e['hangul'].get('widths'):
            rw = e['hangul']
            idx = lambda c, h: h['cho_map'][(c - 0xAC00) // 588] * h['jung_groups'] * h['jong_groups'] + h['jung_map'][(c - 0xAC00) % 588 // 28] * h['jong_groups'] + h['jong_map'][(c - 0xAC00) % 28]
            for c in range(0xAC00, 0xD7A4, 7):
                n += 1
                a = hg['widths'][idx(c, hg)] * sc; b = rw['widths'][idx(c, rw)] if idx(c, rw) < len(rw['widths']) else None
                if b is not None and abs(a - b) > 1.5: bad += 1
        if bad: diff.append((e['name'], e['bold'], e['italic'], bad, n)); continue      # 글꼴 파일 값이 rhwp 값과 다르면(한컴이 따로 잰 값일 수 있다) 이 항목은 rhwp 값을 그대로 둔다
        same += 1
        out.append(dict(name=e['name'], bold=e['bold'], italic=e['italic'], em=pick.em, latin=lat, hangul=hg or e['hangul'], src='local-font'))
    # rhwp 표에 없는 글꼴도 시험 문서에 쓰이고 이 PC 에 설치돼 있으면 만든다(문서 글꼴 이름 그대로)
    known = {(e['name'], e['bold'], e['italic']) for e in out}; rh_names = {e['name'] for e in rh['fonts']}; extra = 0
    names_file = HERE / 'doc_font_names.txt'
    for nm in [l.strip() for l in names_file.read_text(encoding='utf-8').splitlines() if l.strip() and not l.startswith('#')] if names_file.exists() else []:
        if nm in rh_names: continue
        for bold, italic in ((False, False), (True, False), (False, True), (True, True)):
            pk = next((fc for f, fc in by_key.get(norm(nm), []) if matches(fc, nm, bold, italic)), None)
            if pk is None or (nm, bold, italic) in known: continue
            hg = hangul_entry(pk, pk.em)
            out.append(dict(name=nm, bold=bold, italic=italic, em=pk.em, latin=latin_entry(pk), hangul=hg, src='local-font')); extra += 1
    print('rhwp 표에 없는 글꼴 항목 %d개를 이 PC 글꼴로 추가' % extra)
    print('rhwp 항목 %d개 중 이 PC 글꼴로 다시 만든 것 %d개(rhwp 값과 같음 %d, 다름 %d), 이 PC 에 없어 못 만든 것 %d개' % (len(rh['fonts']), len(out), same, len(diff), len(miss)))
    for d in diff[:12]: print('  다름:', d)
    if check: return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump({'source': '이 PC 에 설치된 글꼴 파일의 hmtx 글자 폭(devtools/build_font_metrics.py). 글꼴 파일 자체는 저장하지 않는다.', 'fonts': out}, gzip.open(OUT, 'wt', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('->', OUT, OUT.stat().st_size, '바이트')


if __name__ == '__main__':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    main('--check' in sys.argv)

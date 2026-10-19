"""글꼴 폭 조회(V3 1단계). 입력 = 글꼴 이름(문서에 적힌 한글·영문 이름), 글자 → 출력 = 1em 대비 폭(0~1+).
데이터 출처 세 겹: ① 우리 측정(한컴 PDF 에서 잰 문장부호·공백: MEASURED) ② 이 PC 에 설치된 글꼴 파일에서 직접 읽은 폭표(`data/font_metrics_local.json.gz`, devtools/build_font_metrics.py,
THIRD_PARTY_NOTICES.md 6절) ③ rhwp 폭표(MIT, `data/rhwp_font_metrics.json.gz`, 4절 — 이 PC 에 글꼴이 없거나 값이 달라 ②로 못 만든 항목만).
우리 측정 > 글꼴 파일 폭표 > rhwp 표 > 글자 종류별 기본값.
"""
import gzip, json, re
from pathlib import Path

_DATA = Path(__file__).resolve().parent / 'data' / 'rhwp_font_metrics.json.gz'
_LOCAL = Path(__file__).resolve().parent / 'data' / 'font_metrics_local.json.gz'

# 문서의 글꼴 이름 -> rhwp 폭표 이름. rhwp 의 별칭 해석(font_metrics_data.rs resolve_metric_alias)을 읽기 전의 잠정 표 — 에이전트 조사 결과로 보강한다.
ALIAS = {
    '함초롬바탕': 'HCR Batang', '함초롬돋움': 'HCR Dotum', '맑은 고딕': 'Malgun Gothic', 'Malgun Gothic': 'Malgun Gothic',
    '바탕': 'Batang', '바탕체': 'BatangChe', '돋움': 'Dotum', '돋움체': 'DotumChe', '굴림': 'Gulim', '굴림체': 'GulimChe',
    '한컴바탕': 'HCR Batang', '한컴돋움': 'Haansoft Dotum', 'Haansoft Batang': 'Haansoft Batang', 'Haansoft Dotum': 'Haansoft Dotum',
    '휴먼명조': 'HumanMyeongJo', '한양신명조': 'HanyangSinMyeongJo', '한양중고딕': 'HanyangJungGothic', '한양견명조': 'HanyangKyunMyeongJo', '한양견고딕': 'HanyangKyunGothic',
    'HY헤드라인M': 'HYHeadLine-Medium', 'HY견고딕': 'HYGothic-Extra', 'HY중고딕': 'HYGothic-Medium', 'HY견명조': 'HYMyeongJo-Extra', 'HY신명조': 'HYSinMyeongJo-Medium',
    '신명 중명조': '신명 중명조', '한컴 고딕': '한컴 고딕', '한컴 윤고딕 240': '한컴 윤고딕 240', '한컴 윤고딕 720': '한컴 윤고딕 720',
}

_fonts = None


def _load():
    global _fonts
    if _fonts is None:
        _fonts = {}
        for path in (_LOCAL, _DATA):      # 글꼴 파일에서 읽은 항목이 먼저, rhwp 표는 같은 (이름, 굵기, 기울임) 이 없을 때만
            if not path.exists(): continue
            for f in json.load(gzip.open(path, 'rt', encoding='utf-8'))['fonts']:
                if (f['bold'], f['italic']) in _fonts.get(f['name'].lower(), {}): continue
                f['_lat'] = {c: w for s, e, ws in f['latin'] for c, w in zip(range(s, e + 1), ws)}
                f.setdefault('src', 'rhwp')
                _fonts.setdefault(f['name'].lower(), {})[(f['bold'], f['italic'])] = f
    return _fonts


def find(face, bold=False, italic=False):
    """글꼴 이름 -> rhwp 폭표 항목(없으면 None)."""
    fs = _load()
    name = ALIAS.get(face, face or '').lower()
    v = fs.get(name)
    if not v: return None
    return v.get((bold, italic)) or v.get((bold, False)) or v.get((False, False)) or next(iter(v.values()))


def hangul_width(f, ch):
    """한글 음절(가~힣) 폭(em). rhwp FontMetric::get_width 와 같은 (초·중·종성 그룹) 색인."""
    h = f['hangul']
    if not h: return None
    i = ord(ch) - 0xAC00; cho, jung, jong = i // 588, i % 588 // 28, i % 28
    gi = h['cho_map'][cho] * h['jung_groups'] * h['jong_groups'] + h['jung_map'][jung] * h['jong_groups'] + h['jong_map'][jong]
    return h['widths'][gi] / f['em'] if gi < len(h['widths']) else None


def latin_width(f, ch):
    w = f['_lat'].get(ord(ch))
    return None if w is None else w / f['em']


def _is_halfwidth_form(o): return 0xFF61 <= o <= 0xFFDC or 0xFFE8 <= o <= 0xFFEE


def _is_cjk(o):
    return (0xAC00 <= o <= 0xD7A3 or 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F or 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0xF900 <= o <= 0xFAFF
            or 0x3040 <= o <= 0x30FF or 0x3000 <= o <= 0x303F or 0x2E80 <= o <= 0x2FDF or (0xFF00 <= o <= 0xFFEF and not _is_halfwidth_form(o)))


def _is_fullwidth_symbol(o):
    """DB 에 없으면 전각(1em)으로 치는 기호: 통화(₩€£¥), 화살표, 동그라미·괄호 글자, 로마 숫자, 도형(□○△◆ 등), 별, ㉠ㅤ, ㎜ 류. (rhwp is_fullwidth_symbol 이 가리키는 종류)"""
    return (o in (0x20A9, 0x20AC, 0xA3, 0xA5, 0x2103, 0x2109, 0x2116, 0x2605, 0x2606) or 0x2190 <= o <= 0x21FF or 0x2460 <= o <= 0x24FF or 0x2160 <= o <= 0x217F
            or 0x25A0 <= o <= 0x25FF or 0x2600 <= o <= 0x26FF or 0x3200 <= o <= 0x33FF or 0x2700 <= o <= 0x27BF)


_SANS = re.compile('돋움|고딕|굴림|Gothic|Sans|Dotum|Gulim|HeadLine|Arial|Helvetica|Verdana|Tahoma|Calibri|Malgun')
NARROW_PUNCT = set(",.:;'" + '"`·‘’‧')
NARROW_FACES = ('휴먼명조', '한양중고딕', 'HY중고딕')
# 한컴 합성 사다리 실측(devtools/synth_punct.py punct1, 2026-10-14, 이 PC 한컴오피스 2024, 오차 ±0.004em): 폭표 값이 글리프 없음 대체값(0·1.0)이거나 달랐던 쌍. 폭표보다 먼저 쓴다.
MEASURED = {('한양신명조', '·'): 0.386, ('한양신명조', '–'): 1.0, ('한양신명조', '•'): 1.0, ('한양중고딕', '·'): 0.380, ('한양중고딕', '–'): 1.0, ('한양중고딕', '•'): 1.0,
            ('휴먼명조', '•'): 0.398, ('한컴돋움', '※'): 0.770, ('함초롬돋움', '※'): 0.774}


def advance(face, ch, bold=False, italic=False):
    """글자 한 개의 1em 대비 폭. ① 폭표(우리 측정·rhwp) ② 표에 없으면 글자 종류별 규칙(rhwp 가 DB 미스일 때 쓰는 규칙을 읽고 새로 씀):
    반각 형태(U+FF61~FFDC)·그 밖의 글자 0.5, 한글·한자·가나·전각 기호 1.0, 문장부호 몇 개 0.3. 폭표가 전각(1em)을 주는 일반 구두점(U+2018~2027: 따옴표·말줄임표)은 반각으로 줄인다."""
    m = MEASURED.get((face, ch))
    if m is not None: return m
    f = find(face, bold, italic)
    o = ord(ch)
    w = None
    if f:
        w = hangul_width(f, ch) if 0xAC00 <= o <= 0xD7A3 else latin_width(f, ch)
    if w is not None:
        if 0x2018 <= o <= 0x2027 and w > 0.6: w = 0.5
        return w
    if o < 0x250 and ch != ' ':      # 폭표에 없는 영문 칸 글꼴(HCI Poppy 등): 글자마다 0.5em 이면 콜론·마침표가 넓게 잡혀 '09:00~10:00' 이 칸에 안 들어간다 -> Times(명조 계열)·Arial(고딕 계열) 폭
        g = find('Arial' if _SANS.search(face or '') else 'Times New Roman', bold, italic)
        w2 = latin_width(g, ch) if g else None
        if w2 is not None: return w2
    if _is_halfwidth_form(o): return 0.5
    if _is_cjk(o) or _is_fullwidth_symbol(o): return 1.0
    if ch in NARROW_PUNCT and (face or '') in NARROW_FACES: return 0.3
    return 0.5

"""HWP / HWPX / HTML 통합 진입점. 입력 형식은 확장자가 아니라 내용(매직 바이트)으로 알아내고, 출력 형식은 출력 확장자로 정한다.
    python convert.py 입력파일 출력파일(.html | .hwpx | .pdf) [--approval 담당,검토,확인,승인]
    python convert.py --capabilities      (이 환경에서 되는 변환·옵션·한도·종료 코드를 JSON 으로 출력)
지원: hwp->html, hwp->hwpx(hwp-cli 직접 변환, 없거나 실패하거나 결재선이면 HTML 을 거치는 자체 변환), hwpx->html, html->hwpx, 그리고 (weasyprint 가 있으면) html·hwp·hwpx->pdf.
--approval 을 주면 문서 맨 위 오른쪽에 결재선 표를 넣는다"""
import importlib.util, json, os, re, shutil, struct, subprocess, sys, tempfile, time, urllib.parse, urllib.request, zipfile
from pathlib import Path
import approval as approval_mod
import hwp2html, hwpx2html, html2hwpx
from core import vpos
VPOS_FIX = os.environ.get('VPOS_FIX', 'on')      # off 면 2패스 vpos 되잡기를 끈다
VPOS_MAXBYTES = float(os.environ.get('VPOS_MAXBYTES', 1.9e6))      # 그림(data:)을 뺀 HTML 크기가 이보다 크면(큰 문서) 보정 패스를 건너뛴다. 배치 시간은 이 크기에 거의 비례한다(순위 상관 0.95, 첫 배치 1바이트당 ≈1.4e-5초). pr-1674(2.07MB)가 3번 배치(28+33+36초)+쓰기+HTML 로 117초 걸려 앱 제한(120초)에 닿았다 → 1.9MB 이하만 보정(보정 3번 ≈ 100초 이하).
VPOS_MAXSEC = float(os.environ.get('VPOS_MAXSEC', 40))      # 안전망: 첫 배치가 이 초의 3배(기본 120초)를 넘는 느린 기계에서도 보정 패스를 건너뛴다. 예전엔 이 시간이 기준이라 기계가 바쁘면 쪽 수가 달라졌다(memo_field 40↔41쪽) — 이제 기준은 문서 크기, 시간은 안전망.

OLE2 = bytes.fromhex('D0CF11E0A1B11AE1')
PUA_RE = re.compile('[-\U000f0000-\U000ffffd\U00100000-\U0010fffd]')
HTML_TAG = re.compile(rb'<\s*(!doctype\s+html|html|head|body|meta|title|style|table|div|p|span|h[1-6]|br|img|ul|ol|li|a)\b', re.I)


def inspect(path):
    """(형식, 판별 근거). 근거는 사람이 읽는 문장으로, 화면에 그대로 보여 준다."""
    with open(path, 'rb') as f: head = f.read(8192)
    if head[:8] == OLE2: return 'hwp', 'OLE2 시그니처(D0CF11E0…)'
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            if 'mimetype' in z.namelist() and z.read('mimetype').strip() == b'application/hwp+zip':
                return 'hwpx', 'ZIP 컨테이너 + mimetype=application/hwp+zip'
        raise ValueError('HWPX가 아닌 ZIP 파일')
    if head.startswith(b'HWP Document File V3'): raise ValueError('HWP 3.0 (옛 형식)은 지원하지 않습니다. 한글에서 HWP 5.0 또는 HWPX 로 다시 저장해 주세요')
    if b'\0' in head: raise ValueError('알 수 없는 바이너리 형식 (HWP·HWPX·HTML 아님)')
    m = HTML_TAG.search(head)
    if not m: raise ValueError('텍스트 파일이지만 HTML 태그가 없음')
    return 'html', f'텍스트 + HTML 태그 발견({m.group(0).decode("latin-1")}…)'      # ponytail: 앞 8KB만 본다. UTF-16 HTML은 바이너리로 거부


def detect(path):
    return inspect(path)[0]


def leftover_pua(path):
    """변환된 HTML 에 남은 사설 영역 문자의 코드(글꼴에 따라 □ 로 보인다). 모르는 기호를 조용히 놓치지 않으려고 센다."""
    return sorted({ord(c) for c in PUA_RE.findall(Path(path).read_text(encoding='utf-8'))})


def _read_html(src):
    """HWPX 조립기·PDF 엔진은 UTF-8 글자로 읽는다. CP949(옛 한글 HTML)·BOM 은 여기서 글자로 바꿔 쓴다."""
    raw = Path(src).read_bytes()
    for enc in ('utf-8-sig', 'cp949'):
        try: return raw.decode(enc)
        except UnicodeDecodeError: pass
    raise ValueError('인코딩을 알 수 없는 HTML (UTF-8·CP949만 지원)')


def _via_html(first, sink):
    """입력 -> (first 로) HTML -> (결재선 끼움) -> sink(HTML 글, 출력 경로, 임시 폴더). first 가 None 이면 입력이 이미 HTML."""
    def run(src, dst, approval=None):
        with tempfile.TemporaryDirectory() as d:
            if first:
                mid = Path(d) / 'mid.html'; first(src, str(mid)); text = mid.read_text(encoding='utf-8')
            else: text = _read_html(src)
            if approval: text = approval_mod.add(text, approval)
            return sink(text, dst, Path(d))
    return run


def _to_hwpx(text, dst, d):
    mid = d / 'in.html'; mid.write_bytes(text.encode('utf-8'))      # write_text 는 Windows 에서 줄바꿈을 바꾼다
    return html2hwpx.build(str(mid), dst)


# 반각 꺾쇠·마침표(공문서 ｢ ｣ 제목 표시)는 PDF 용 나눔 글꼴에 글자가 없어 네모(⊠)로 나온다 -> 모양이 같은 전각 글자로 바꿔서 찍는다(HTML 에는 원문 그대로)
HALFWIDTH_CJK = {0xFF61: '。', 0xFF62: '「', 0xFF63: '」', 0xFF64: '、'}


# PDF 는 한컴 글꼴 대신 나눔 글꼴로 찍으니 한글이 2~6% 좁다 -> 변환기가 HTML 에 따로 적어 둔 폭 보정(--hd)을 자간(--ls)에 더한다(hwp2html.spacing_css).
# HTML 을 브라우저로 볼 때는 더하지 않는다(브라우저에는 진짜 한컴 글꼴이 있어 보정하면 글이 넓어져 줄이 먼저 꺾인다).
PDF_CSS = ('[style*="--ws:"]{word-spacing:var(--ws)!important} [style*="--hd:"]{letter-spacing:calc(var(--ls,0em) + var(--hd))!important} .mo.mm,.hwp-run,.hwp-pgn{display:block!important}'
           # HWP 를 HTML 로 내보낼 때 hwp2html 이 담아 둔 '한컴이 저장한 줄·쪽 끝 처리' 표시를 PDF 에서만 켠다(브라우저는 몰라서 모양이 안 바뀐다) — PDF 직통(저장 모드)과 같은 결과가 나오게 한다
           '.hwp-ln{display:block!important;white-space:nowrap!important}.hwp-lp{display:block!important;white-space:pre!important}.hwp-ln.hwp-lj,.hwp-lp.hwp-lj{text-align-last:justify!important}'      # 저장된 줄마다 한 줄 상자(HWP 는 nowrap, HWPX 는 pre)
           'p.hwp-tf,div.hwp-tf{line-height:1!important;margin-top:var(--tt)!important;margin-bottom:var(--tb)!important}'
           'td.hwp-nh{height:auto!important}'      # 셀 단위로 나뉘는 표의 찬 행: 높이를 빼서 줄 단위로 나뉘게
           '.hwp-wsp{display:none!important}.hwp-wsw{padding-top:var(--wpt)!important;padding-bottom:var(--wpb)!important;margin-bottom:var(--wmb)!important}.hwp-wsb{break-before:page!important}')      # 표와 같은 줄의 공백 문단


_HANGUL_PAIR = re.compile('(?<=[가-힣])(?=[가-힣])')


def _keep_words(text):
    """WeasyPrint 는 word-break:keep-all 을 몰라 한글 낱말 한가운데서 줄을 꺾는다('연구개발계획서' 가 '연구' / '개발계획서' 로 갈라짐; 한컴·브라우저는 어절째 다음 줄로 보낸다).
    변환기가 낸 HTML 은 keep-all 이 기본이라, PDF 로 찍을 때만 한글 글자 사이에 WORD JOINER(U+2060: 안 보이고 PDF 글에도 안 남는다)를 끼워 어절 가운데 줄 꺾임을 막는다.
    글자 단위로 줄을 나누는 문단(word-break:normal 또는 break-all)·<style>·<title> 은 그대로 둔다. keep-all 을 안 쓴 외부 HTML 도 그대로 둔다."""
    if 'word-break:keep-all' not in text: return text
    out, mode = [], None        # mode: None 보통 · 'raw' <style>/<title> 안 · 'ball' break-all 문단 안
    for tok in re.split(r'(<[^>]*>)', text):
        if tok[:1] == '<':
            t = tok.lower()
            if mode is None and t.startswith(('<style', '<title')): mode = 'raw'
            elif mode == 'raw' and t.startswith(('</style', '</title')): mode = None
            elif mode is None and t.startswith('<p') and ('word-break:normal' in t or 'word-break:break-all' in t): mode = 'ball'      # 글자 단위 줄 나눔 문단(normal)·외부 HTML 의 break-all 은 그대로
            elif mode == 'ball' and t.startswith('</p'): mode = None
        elif mode is None: tok = _HANGUL_PAIR.sub('\u2060', tok)
        out.append(tok)
    return ''.join(out)


# 글자 간격(letter-spacing)은 문단 마지막 글자 뒤에도 붙어 줄 폭을 한 번 더 먹는다. 칸 폭에 아슬아슬하게 들어가는 '[공급기업]' 의 '업]' 이 아래 줄로 내려가던 원인이라(한컴은 한 줄)
# 폭 보정(--hd)이 붙은 문단의 마지막 글자만 따로 떼어 간격 0 으로 찍는다. 음수 margin-right 는 WeasyPrint 가 줄 폭 계산에 안 쓴다(시험).
_TAIL = re.compile(r'<span style="([^"]*--hd:[^"]*)">([^<]*[^<\s;])</span></p>')


def _tail_spacing(m):
    st = ';'.join(x for x in m.group(1).split(';') if x and not x.startswith(('letter-spacing', '--hd', '--ls')))
    return f'<span style="{m.group(1)}">{m.group(2)[:-1]}</span><span style="{st};letter-spacing:0">{m.group(2)[-1]}</span></p>'


FIT_MIN = float(os.environ.get('FIT_MIN') or 1.02)        # 넘침 비율이 이보다 클 때만 줄인다(99 면 줄이기를 끈다)
FIT_MAX = float(os.environ.get('FIT_MAX') or 2.0)        # HTML 이 쪽보다 넓을 때 줄여 맞추는 한계(2배 = 50%). 브라우저(Chromium 인쇄)도 최대 2배까지만 줄이고 더 넓은 건 잘린다 — 3배로 했더니 넓은 문서가 기준(Edge)보다 훨씬 작게 찍혀 유사도가 내렸다(html 세트 h1)


def _local_fetcher(base):
    """HTML 파일이 있는 폴더 안의 file: 자원(그림·CSS)과 data: 만 읽는다. 폴더 밖 경로·http(s)·다른 호스트의 file: 은 막는다(막힌 자원은 빠질 뿐 변환은 계속)."""
    from weasyprint.urls import URLFetcher
    root = Path(base).resolve()
    class Local(URLFetcher):
        def fetch(self, url, headers=None):
            if url[:5].lower() == 'file:':
                u = urllib.parse.urlparse(url)
                if u.netloc not in ('', 'localhost'): raise ValueError('원격 file 주소는 막는다')
                p = Path(urllib.request.url2pathname(u.path)).resolve()
                if p != root and root not in p.parents: raise ValueError('HTML 폴더 밖의 파일은 읽지 않는다')
            return super().fetch(url, headers)
    return Local(allowed_protocols=('data', 'file'))


def _overflow_ratio(doc):
    """쪽 내용 영역 폭 대비 블록·표·그림 상자가 오른쪽으로 뻗은 비율의 최대값(1 이면 안 넘침). 잘라서 숨기는(overflow 가 visible 이 아닌) 상자 안은 안 센다."""
    from weasyprint.formatting_structure import boxes
    ratio = 1.0
    for page in doc.pages:
        pb = page._page_box; left = pb.content_box_x(); far = left
        stack = [c for c in pb.children if not isinstance(c, boxes.MarginBox)]
        while stack:
            b = stack.pop()
            if isinstance(b, (boxes.BlockBox, boxes.TableBox, boxes.ReplacedBox)): far = max(far, b.position_x + b.margin_width())      # 글줄·낱말 상자는 안 센다: 긴 코드 한 줄이 삐져나왔다고 문서 전체를 줄이면 Edge 보다 훨씬 작게 찍힌다(쉬운_설명 보고서 44→20쪽, 기준 40쪽)
            if getattr(b.style, 'overflow', 'visible') == 'visible': stack.extend(getattr(b, 'children', None) or [])
        if pb.width > 0: ratio = max(ratio, (far - left) / pb.width)
    return ratio


def _is_ours(text):
    """이 변환기가 만든 HTML 인가(표 클래스 hwp-table·머리말 hwp-header 등 자기 표지). 그런 HTML 은 한컴 쪽 크기·표 폭을 그대로 담아 쪽에 맞춰 줄이면 안 된다(한컴 표는 본문 폭을 조금 넘는 일이 흔하고, 줄였더니 사용자 holdout 0.582→0.421)."""
    return 'hwp-table' in text or 'class="hwp-' in text


STYLE_CLASSES = os.environ.get('STYLE_CLASSES', 'on') != 'off'      # PDF 로 찍기 전에 되풀이되는 style 속성을 클래스로 묶는다(느린 변환의 한 원인: 국립국어원 HTML 의 79% 가 style 속성인데 서로 다른 것은 11,284개 중 1,948개)
_STYLED_TAG = re.compile(r'<(p|span|div|td|th|tr|table|col)(?=[\s>/])([^>]*)>')
_STYLE_ATTR = re.compile(r'\sstyle="([^"]*)"')
_CLASS_ATTR = re.compile(r'\sclass="([^"]*)"')


def _style_classes(text):
    """되풀이되는 style="…"(40자 이상, 2번 이상)을 class="hzN" 으로 바꾸고 `.hzN`(클래스 5번 겹쳐 인라인 style 보다 약하지 않게)로 <style> 에 넣는다. 인라인 style 은 어떤 선택자보다 세므로
    PDF_CSS 의 '[style*="--ws:"]'·'[style*="--hd:"]' 규칙(style 글자에 의존)도 클래스마다 같은 규칙을 더해 준다. SVG 안쪽 태그는 건드리지 않는다(목록 태그만)."""
    if not STYLE_CLASSES: return text
    cnt = {}
    for m in _STYLED_TAG.finditer(text):
        a = _STYLE_ATTR.search(m.group(2))
        if a and len(a.group(1)) >= 40: cnt[a.group(1)] = cnt.get(a.group(1), 0) + 1
    names = {st: 'hz%d' % i for i, st in enumerate((k for k, v in cnt.items() if v >= 2))}
    if not names: return text
    def one(m):
        a = _STYLE_ATTR.search(m.group(2)); nm = names.get(a.group(1)) if a else None
        if not nm: return m.group(0)
        rest = m.group(2)[:a.start()] + m.group(2)[a.end():]
        c = _CLASS_ATTR.search(rest)
        rest = (rest[:c.start()] + ' class="%s %s"' % (c.group(1), nm) + rest[c.end():]) if c else rest + ' class="%s"' % nm
        return '<%s%s>' % (m.group(1), rest)
    out = _STYLED_TAG.sub(one, text)
    sel = lambda n: '.' + '.'.join([n] * 5)
    rules = ''.join('%s{%s}' % (sel(n), st.rstrip(';')) + ('%s{word-spacing:var(--ws)!important}' % sel(n) if '--ws:' in st else '') + ('%s{letter-spacing:calc(var(--ls,0em) + var(--hd))!important}' % sel(n) if '--hd:' in st else '') for st, n in names.items())
    i = out.find('</style>')
    return out[:i] + chr(10) + rules + out[i:] if i >= 0 else out


_DATA_URI = re.compile(r'data:[^"\x27)]*')      # 그림 데이터(base64): 배치 시간에 영향이 적어 크기 어림에서 뺀다


def _wp(text, hk):
    import weasyprint
    return weasyprint.HTML(string=_style_classes(text) if _is_ours(text) or 'data-pi="' in text else text, **hk)      # 우리 변환기가 만든 HTML 에만: 외부 HTML 은 자기 CSS(#id 선택자·!important)가 클래스 스타일을 이길 수 있어 인라인 style 을 그대로 둔다


def _to_pdf(text, dst, d, keep_words=False, base=None):
    """keep_words: HTML 파일에서 바로 PDF 로 갈 때만 켠다(어절 안 끊기). HWP·HWPX 에서 바로 갈 때는 저장된 줄 끊김대로 찍어서 켜지 않는다 — 켜면 공개 108건 쪽 수 일치가 70→67 로 줄었다(인수인계 문서 2026-10-12).
    HTML 입력(keep_words)일 때만: ① 옛 HTML 속성(table border·cellpadding·bgcolor·<font size>…)을 읽고(presentational_hints) ② base(입력 폴더) 안의 그림·CSS 를 읽고 ③ 쪽보다 넓은 내용은 브라우저 인쇄처럼 쪽에 맞춰 줄인다."""
    import weasyprint
    from weasyprint.urls import URLFetcher
    # 기본은 data: 주소만 읽는다. file://·http:// 를 열면 내 컴퓨터 파일이나 내부망 주소가 새어 나갈 수 있어 막는다(막힌 자원은 빠질 뿐 변환은 계속)
    text = text.translate(HALFWIDTH_CJK)
    if keep_words and not _is_ours(text): text = _keep_words(text)      # 우리 HTML 은 직통과 같이 찍는다(어절 보호를 켜면 저장된 줄이 없는 HWPX 에서 줄이 일찍 꺾여 쪽이 늘었다: 80168 157→161쪽)
    text = _TAIL.sub(_tail_spacing, text)
    kw = {'presentational_hints': True} if keep_words else {}
    hk = {'base_url': Path(base).resolve().as_uri() + '/', 'url_fetcher': _local_fetcher(base)} if base else {'url_fetcher': URLFetcher(allowed_protocols=('data',))}
    css = [weasyprint.CSS(string=PDF_CSS)]
    cost = len(_DATA_URI.sub('', text))      # 레이아웃 비용 어림: 그림 데이터를 뺀 HTML 크기
    t0 = time.time(); doc = _wp(text, hk).render(stylesheets=css, **kw); zoom = 1.0; ftext = text; fxu, bru = {}, {}      # ftext: 지금 doc 을 만든 HTML, fxu·bru: 거기에 쓴 위치 보정·쪽 나눔
    if VPOS_FIX != 'off' and 'data-pi="' in text and vpos.trusted(text) and cost <= VPOS_MAXBYTES and time.time() - t0 < 3 * VPOS_MAXSEC:      # 2패스 vpos 되잡기(core/vpos.py): 문단 위치를 한컴 저장 vpos 에 맞춰 위 간격을 고치고 다시 배치
        ms = vpos.measure(doc); fx = vpos.fixes(ms); br = vpos.breaks(ms, vpos.usable(ms) and not re.search(r'column-count:\s*[2-9]|name="hwp-multicol"', text))      # br: 한컴은 쪽을 바꾼 자리인데 우리는 한 쪽에 더 담는 곳(다단 문서는 단이 바뀔 때도 저장 위치가 되돌아가니 뺀다)
        if fx or br:
            doc2 = _wp(vpos.apply(text, fx, br), hk).render(stylesheets=css, **kw)
            if vpos.prefer_first(vpos.stored_pages(ms), len(doc.pages), len(doc2.pages)):      # 2패스가 쪽을 늘렸고 저장 쪽 수가 1패스에 더 가까우면: 위로 당기기만(쪽을 못 늘린다) 적용해 본다(underline_run 6→7쪽·pr-1674 37→38쪽이 되던 것)
                neg = {k: v for k, v in fx.items() if v[0] < 0}
                if neg or br:
                    doc3 = _wp(vpos.apply(text, neg, br), hk).render(stylesheets=css, **kw)
                    if len(doc3.pages) <= len(doc.pages): doc = doc3; ftext = vpos.apply(text, neg, br); fxu, bru = neg, br
            else: doc = doc2; ftext = vpos.apply(text, fx, br); fxu, bru = fx, br
        ov = vpos.overlaps(doc, fxu) if fxu else {}      # 위로 당긴 글이 앞 표·그림 아랫선을 파고들면 그 문단은 겹친 만큼 덜 당겨 다시 배치(쪽이 늘면 버린다)
        if ov:
            fx2 = {**fxu, **{pi: (min(0.0, fxu[pi][0] + o), fxu[pi][1]) for pi, o in ov.items()}}
            doc5 = _wp(vpos.apply(text, fx2, bru), hk).render(stylesheets=css, **kw)
            if len(doc5.pages) <= len(doc.pages): doc = doc5; ftext = vpos.apply(text, fx2, bru); fxu = fx2
        if vpos.SLACK == 'on' and cost <= VPOS_MAXBYTES / 2 and time.time() - t0 < 3 * VPOS_MAXSEC and not re.search(r'column-count:\s*[2-9]|name="hwp-multicol"', text):      # 쪽 끝 허용: 한컴 저장 위치가 증명하는 쪽에만 아래 여백을 줄여 한 번 더 배치(쪽이 늘면 버린다)
            sl = vpos.slacks(doc, vpos.measure(doc))
            if sl:
                doc4 = _wp(ftext, hk).render(stylesheets=css + [weasyprint.CSS(string=vpos.slack_css(sl))], **kw)
                if len(doc4.pages) <= len(doc.pages): doc = doc4
    if keep_words and base and not _is_ours(text):
        r = _overflow_ratio(doc)
        if r > FIT_MIN:      # 쪽을 r 배 크게 잡고 배치한 뒤 PDF 로는 1/r 로 줄여 쓴다(쪽 나눔도 줄인 크기대로)
            r = min(r, FIT_MAX); pb = doc.pages[0]._page_box
            css.append(weasyprint.CSS(string='@page{size:%gpx %gpx!important;margin:%gpx %gpx %gpx %gpx!important}' % tuple(round(v * r, 2) for v in (pb.margin_width(), pb.margin_height(), pb.margin_top, pb.margin_right, pb.margin_bottom, pb.margin_left))))
            doc = _wp(text, hk).render(stylesheets=css, **kw); zoom = 1 / r
    if os.environ.get('VPOS_SCORE') and 'data-pi="' in text:      # 시험용: 문단별 (쪽, 쪽 위 위치, 한컴 저장 위치)를 PDF 옆 JSON 으로 남긴다 — 설정 후보를 저장 위치로 고르는 점수 검증(devtools/cfg_score.py)
        import json; json.dump({'pages': len(doc.pages), 'ms': [(m['pi'], m['page'], m['end'], round(m['rel'], 2), m['vp']) for m in vpos.measure(doc)]}, open(str(dst) + '.score.json', 'w'))
    doc.write_pdf(dst, zoom=zoom)
    return {'pages': len(doc.pages)}


def _html_pdf(src, dst, approval=None):
    """HTML -> PDF. 입력 HTML 과 같은 폴더의 그림·CSS 를 쓸 수 있다(앱은 업로드 파일만 든 임시 폴더라 아무것도 안 열린다)."""
    text = _read_html(src)
    if approval: text = approval_mod.add(text, approval)
    return _to_pdf(text, dst, None, keep_words=True, base=Path(src).resolve().parent)


def _to_html(conv):
    """HTML 로 내보내는 변환기에 결재선 옵션을 붙인다."""
    def run(src, dst, approval=None):
        r = conv(src, dst)
        if approval: approval_mod.add_to_file(dst, approval)
        return r
    return run


HWP_CLI_TIMEOUT = 60        # 초. 앱의 변환 제한(120초)보다 훨씬 짧게, 넘으면 자체 변환기로 바꿀 여유가 있어야 한다. 그림 많은 66MB 문서: 앱(업로드를 컨테이너 메모리 폴더에 둠)에서 hwp-cli 8.5초(결과 62MB)·자체 변환 4.6초(0.5MB). 같은 파일을 윈도 폴더 마운트로 읽으면 90초대로 느려진다(시험할 때 주의)
LOSS_TEXT = {'control_removed': '컨트롤(양식 입력칸·체크박스 등)', 'opaque_control_unrepresentable': 'HWPX 로 표현 못 하는 개체'}      # hwp-cli 손실 보고서 코드 -> 사람이 읽는 말


def find_hwp_cli():
    """hwp-cli 실행 파일 경로: 환경변수 HWP_CLI -> PATH 의 hwp(컨테이너는 /usr/local/bin/hwp) -> 프로젝트 tools/hwp-cli/hwp.exe(개발용). 없으면 None."""
    p = os.environ.get('HWP_CLI')
    if p in ('off', '0'): return None      # 끄기(자체 변환기만 쓰기·비교 시험용)
    if p and Path(p).is_file(): return p
    w = shutil.which('hwp')
    if w: return w
    dev = Path(__file__).resolve().parents[0] / 'tools' / 'hwp-cli' / 'hwp.exe'
    return str(dev) if dev.is_file() else None


# hwp-cli 는 떠 있는(글자처럼 취급이 아닌) 개체의 배치를 한 가지로 뭉갠다. 코퍼스 실측(2026-10-13, 원본 HWP 값 대 hwp-cli 결과, 괄호는 원본과 일치한 수):
#   그림 62장    — 배치 '글 앞으로'로 고정(2), 문단과 함께 흐름 끔(4), 겹침 허용 켬(14), 가로 기준 '문단'(4)
#   도형·글상자·선 120개 — 겹침 허용 켬(33), 흐름 끔(24), 가로 기준 '문단'(84), 세로 기준 '문단'(112), 배치 일부(81)
#   표 235개     — 겹침 허용 켬(33), 배치 '자리 차지'로 고정(168). 흐름·기준·정렬은 맞다.
# 그래서 사진이 칸에 묶이지 않고 한 자리에 겹친다(안전관리 회의록, 사용자가 한글에서 확인) -> 원본 HWP 의 값으로 되돌린다.
# 오프셋은 건드리지 않는다: hwp-cli 가 맞게 쓰고(음수는 부호 없는 32비트 정수 — 한컴이 만든 HWPX 55건도 그렇게 쓰고 '-' 부호는 0건), '-' 로 고쳐 쓰면 한글이 못 읽을 수 있다.
OBJ_WRAP = ('SQUARE', 'TOP_AND_BOTTOM', 'BEHIND_TEXT', 'IN_FRONT_OF_TEXT')       # 개체 속성 비트 21~23: 어울림·자리 차지·글 뒤로·글 앞으로(공식 문서 표 70 의 이름은 실제 파일과 다르다)
OBJ_VREL, OBJ_VALIGN = ('PAPER', 'PAGE', 'PARA'), ('TOP', 'CENTER', 'BOTTOM', 'INSIDE', 'OUTSIDE')      # 비트 3~4 · 5~7
OBJ_HREL, OBJ_HALIGN = ('PAPER', 'PAGE', 'COLUMN', 'PARA'), ('LEFT', 'CENTER', 'RIGHT', 'INSIDE', 'OUTSIDE')      # 비트 8~9 · 10~12
HP_NS = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'
DRAW_TAGS = ('rect', 'ellipse', 'arc', 'polygon', 'curve', 'line', 'connectLine', 'textart', 'container', 'ole')      # 그림(pic)을 뺀 그리기 개체
OBJ_LABEL = {'pic': '그림', 'shape': '도형', 'tbl': '표'}
OBJ_FIX = [k for k in (os.environ.get('OBJ_FIX') or 'pic,shape,tbl').split(',') if k in OBJ_LABEL]      # 되돌릴 개체 종류. 그림만 한글에서 확인했다(사용자, 2026-10-13) — 표·도형이 한글에서 이상하면 OBJ_FIX=pic 으로 끈다(off 면 전부 끔)
CTRL_GSO, CTRL_TBL = b' osg', b' lbt'        # CTRL_HEADER 의 컨트롤 ID 는 거꾸로 저장된다('gso ', 'tbl ')


def src_objs(src):
    """원본 HWP 의 개체를 문서 순서대로 {'pic': 그림 하나인 개체, 'shape': 그림 없는 개체(글상자·선·묶음), 'tbl': 표} -> [(폭, 높이, 속성)](HWPUNIT).
    그림이 둘 이상 든 묶음 개체가 있으면 그림·도형 목록은 None(HWPX 쪽 개체와 짝이 흐트러진다)."""
    hwp2html.load(src); out, n, grouped = {'pic': [], 'shape': [], 'tbl': []}, 0, False
    def pics_in(x):      # 이 개체 자신의 그림 수. 안에 든 다른 개체(글상자 속 그림)는 그 개체가 따로 센다
        return sum(1 if y.tag == 85 else 0 if y.tag == 71 else pics_in(y) for y in x.ch)
    def walk(x):
        nonlocal grouped
        for ch in x.ch:
            if ch.tag == 71 and ch.p[:4] in (CTRL_GSO, CTRL_TBL):
                w, h = struct.unpack_from('<II', ch.p, 16); rec = (w, h, struct.unpack_from('<I', ch.p, 4)[0])
                if ch.p[:4] == CTRL_TBL: out['tbl'].append(rec)
                else:
                    k = pics_in(ch); grouped |= k > 1
                    out['pic' if k == 1 else 'shape'].append(rec)
            walk(ch)
    while True:
        try: raw = hwp2html.c.read('/BodyText/Section%d' % n)
        except KeyError: break
        n += 1; walk(hwp2html.tree(hwp2html.records(hwp2html.dec(raw))))
    if grouped: out['pic'] = out['shape'] = None
    return out


def _restore(e, a, kind):
    """HWPX 개체 요소 e(그림·도형·표)의 배치 속성을 원본 개체 속성 a 로 되돌린다. 글자처럼 취급이면 그대로 둔다. 되돌렸으면 True."""
    pos = e.find(HP_NS + 'pos')
    if a & 1 or pos is None: return False
    pick = lambda names, i: names[i] if i < len(names) else None
    vals = {'allowOverlap': str(a >> 14 & 1)}
    if kind != 'tbl':      # 표는 흐름·기준·정렬이 이미 맞다
        vals.update(vertRelTo=pick(OBJ_VREL, a >> 3 & 3), vertAlign=pick(OBJ_VALIGN, a >> 5 & 7), horzRelTo=pick(OBJ_HREL, a >> 8 & 3), horzAlign=pick(OBJ_HALIGN, a >> 10 & 7), flowWithText=str(a >> 13 & 1))
    for k, v in vals.items():
        if v is not None: pos.set(k, v)
    wrap = pick(OBJ_WRAP, a >> 21 & 7)
    if wrap: e.set('textWrap', wrap)
    return True


def _same_size(e, w, h):
    sz = e.find(HP_NS + 'sz')
    return sz is not None and abs(int(sz.get('width')) - w) <= 2 and abs(int(sz.get('height')) - h) <= 2


def fix_obj_pos(src, hwpx):
    """hwp-cli 가 만든 HWPX 의 떠 있는 그림·도형·표 배치를 원본 HWP 값으로 되돌린다. {'pic': 개수, 'shape': 개수, 'tbl': 개수}(되돌린 것만)를 돌려 준다.
    ponytail: 종류별로 문서 순서대로 짝짓고 개수·크기가 모두 같을 때만 고친다. hwp-cli 가 개체를 빠뜨린 문서(그림은 코퍼스 35건 중 12건)나 묶음 개체가 있으면 그 종류는 안 건드린다
    — 크기·앵커로 짝지으면 더 많이 고칠 수 있다."""
    from lxml import etree
    objs = src_objs(src)
    with zipfile.ZipFile(hwpx) as zin:
        names = sorted((n for n in zin.namelist() if re.fullmatch(r'Contents/section\d+\.xml', n)), key=lambda n: int(re.findall(r'\d+', n)[0]))
        roots = {n: etree.fromstring(zin.read(n), etree.XMLParser(huge_tree=True)) for n in names}
        local = lambda e: e.tag[len(HP_NS):] if isinstance(e.tag, str) and e.tag.startswith(HP_NS) else ''
        found = {'pic': [e for n in names for e in roots[n].iter(HP_NS + 'pic')],
                 'shape': [e for n in names for e in roots[n].iter() if local(e) in DRAW_TAGS and e.get('groupLevel', '0') == '0'],      # 묶음 안 개체(groupLevel>0)는 묶음이 따로 갖는다
                 'tbl': [e for n in names for e in roots[n].iter(HP_NS + 'tbl')]}
        done = {}
        for kind, els in found.items():
            want = objs[kind] if kind in OBJ_FIX else None
            if not want or len(els) != len(want) or not all(_same_size(e, w, h) for e, (w, h, _) in zip(els, want)): continue
            done[kind] = sum(_restore(e, a, kind) for e, (_, _, a) in zip(els, want))
        done = {k: v for k, v in done.items() if v}
        if not done: return {}
        new = {}
        for n in names:
            raw = zin.read(n); decl = re.match(rb'<\?xml[^>]*\?>\s*', raw)
            new[n] = (decl.group(0) if decl else b'') + etree.tostring(roots[n], encoding='UTF-8')
        tmp = Path(str(hwpx) + '.tmp')
        with zipfile.ZipFile(tmp, 'w') as zout:      # mimetype 은 첫 항목·무압축 그대로. 이미 압축된 그림이 크니 압축은 가볍게(level 1)
            for it in zin.infolist():
                zi = zipfile.ZipInfo(it.filename, it.date_time); zi.compress_type, zi.external_attr, zi.create_system = it.compress_type, it.external_attr, it.create_system
                zout.writestr(zi, new.get(it.filename) or zin.read(it.filename), compresslevel=1)
    os.replace(tmp, hwpx)
    return done


def _hwp_to_hwpx(src, dst, approval=None):
    """HWP -> HWPX 는 hwp-cli 가 원본 구조를 그대로 옮긴다(HTML 을 거치는 자체 변환보다 글이 빠지지 않고 쪽 수가 한컴에 가깝다: 공개 문서 25건 글 보존 100% 대 96%).
    hwp-cli 가 없거나, 실패하거나, 결재선을 넣어야 하면(HTML 에 끼우는 방식이라) 자체 변환기로 바꾼다. 손실 보고서는 '경고:' 로 알린다.
    hwp-cli 가 뭉갠 떠 있는 그림·도형·표의 배치는 원본 값으로 되돌린다(fix_obj_pos)."""
    own = _via_html(hwp2html.convert, _to_hwpx)
    fallback = lambda s, d, a: {**own(s, d, a), 'engine': '자체(hwp2html → html2hwpx)'}
    exe = find_hwp_cli()
    if approval:
        if exe: print('경고: 결재선은 자체 변환기로만 넣을 수 있어 hwp-cli 대신 자체 변환기를 썼습니다(표 모양 재현이 덜 정확할 수 있음)', file=sys.stderr)
        return fallback(src, dst, approval)
    if not exe: return fallback(src, dst, approval)
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / 'o.hwpx'       # 출력 이름을 짧게: hwp-cli 윈도 빌드는 긴 출력 이름(약 28자 초과)에서 SetFileSecurityW 오류로 실패한다
        try:
            r = subprocess.run([exe, 'convert', str(Path(src).resolve()), '-o', 'o.hwpx', '--loss-report', 'loss.json'], cwd=d, capture_output=True, timeout=HWP_CLI_TIMEOUT)
            if r.returncode or not out.is_file() or not zipfile.is_zipfile(out): raise RuntimeError(f'종료 코드 {r.returncode}')
        except (subprocess.TimeoutExpired, OSError, RuntimeError) as e:
            print(f'경고: hwp-cli 변환이 실패해({type(e).__name__}) 자체 변환기로 바꿨습니다', file=sys.stderr)
            return fallback(src, dst, approval)
        try: fixed = fix_obj_pos(src, out)
        except ValueError: fixed = {}      # 우리가 못 읽는 원본(배포용 등)은 되돌릴 값을 얻을 수 없다
        except Exception as e:      # 되돌리지 못해도 hwp-cli 결과는 그대로 쓴다(낡은 방식으로)
            fixed = {}; print(f'경고: 개체 배치를 원본대로 되돌리지 못했습니다({type(e).__name__}) — 떠 있는 그림·도형이 칸에서 벗어나 보일 수 있습니다', file=sys.stderr)
        shutil.copyfile(out, dst)
        try: events = json.loads((Path(d) / 'loss.json').read_text(encoding='utf-8')).get('events', [])
        except (OSError, ValueError): events = []
        lost = [f'{LOSS_TEXT[e["code"]]} {e["count"]}개' for e in events if e.get('code') in LOSS_TEXT]
        if lost: print('경고: hwp-cli 변환에서 옮겨지지 않은 항목: ' + ', '.join(lost), file=sys.stderr)
        return {'engine': 'hwp-cli' + (f'({"·".join(f"{OBJ_LABEL[k]} {v}개" for k, v in fixed.items())} 배치 복원)' if fixed else ''), 'bytes': Path(dst).stat().st_size}


def _stored_pdf(conv):
    """PDF 로 갈 때만 한컴이 저장한 줄 끊김(HWP PARA_LINE_SEG·HWPX linesegarray)을 따른다. 글꼴 폭이 달라도 한 문단의 줄 수·줄 끊는 자리가 한컴과 같아져
    표 행 높이·쪽 수가 맞는다(공개 108건 모양 유사도 0.408→0.427, 글 위치 오차 42→31pt). HTML 보기·HWPX 로 가는 길은 줄을 새로 흘려 쓰도록 그대로 둔다.
    끄려면 환경변수 STORED_LAYOUT=off. 저장된 줄 정보가 없거나 0 인 파일은 변환기가 알아서 건너뛴다."""
    def run(src, dst):
        mods = (hwp2html, hwpx2html); old = [m.STORED for m in mods]
        for m in mods: m.STORED = os.environ.get('STORED_LAYOUT', 'lines') != 'off'
        try: return conv(src, dst)
        finally:
            for m, o in zip(mods, old): m.STORED = o
    return run


ROUTES = {('hwp', 'html'): _to_html(hwp2html.convert), ('hwpx', 'html'): _to_html(hwpx2html.convert),   # (입력 형식, 출력 형식) -> 변환 함수(src, dst, approval=None)
          ('html', 'hwpx'): _via_html(None, _to_hwpx), ('hwp', 'hwpx'): _hwp_to_hwpx}
if importlib.util.find_spec('weasyprint'):      # PDF 는 weasyprint(+Pango, 한글 글꼴)가 깔린 곳(컨테이너)에서만. 없으면 길 표에서 빠져 화면에도 안 나온다
    ROUTES.update({('html', 'pdf'): _html_pdf, ('hwp', 'pdf'): _via_html(_stored_pdf(hwp2html.convert), _to_pdf),
                   ('hwpx', 'pdf'): _via_html(_stored_pdf(hwpx2html.convert), _to_pdf)})


ENGINES = {('hwp', 'html'): 'hwp2html(자체)', ('hwpx', 'html'): 'hwpx2html(자체)', ('html', 'hwpx'): 'html2hwpx(자체)',
           ('hwp', 'hwpx'): 'hwp-cli 직접 변환(없거나 실패하거나 결재선이면 자체)', ('html', 'pdf'): 'WeasyPrint(어절 보호)',
           ('hwp', 'pdf'): 'hwp2html → WeasyPrint(한컴이 저장한 줄 끊김대로)', ('hwpx', 'pdf'): 'hwpx2html → WeasyPrint(한컴이 저장한 줄 끊김대로)'}


def capabilities():
    """기계가 읽는 자기 설명: 이 환경에서 되는 변환 길·옵션·한도·환경변수·종료 코드·거절하는 입력(사람은 README 를 보면 된다).
    한도 중 변환 제한 시간·동시 변환 수는 app.py 의 값과 같아야 한다(시험이 대조한다)."""
    return {
        'name': 'file-conversation', 'detect_input': '확장자가 아니라 내용(매직 바이트)으로 판별', 'inputs': ['hwp', 'hwpx', 'html'],
        'output_by_extension': {'.html': 'html', '.htm': 'html', '.hwpx': 'hwpx', '.pdf': 'pdf'},
        'routes': [{'from': a, 'to': b, 'engine': ENGINES[(a, b)]} for a, b in sorted(ROUTES)],
        'pdf_available': ('hwp', 'pdf') in ROUTES, 'hwp_cli_available': find_hwp_cli() is not None,
        'options': [{'flag': '--approval', 'value': '담당,검토,확인,승인(쉼표로 구분, 값을 생략하면 기본값)', 'effect': '문서 맨 위 오른쪽에 결재선 표를 넣는다. hwp→hwpx 는 hwp-cli 대신 자체 변환기로 바뀐다'},
                    {'flag': '--capabilities', 'effect': '이 JSON 을 출력하고 끝낸다'}],
        'limits': {'upload_bytes': hwp2html.MAX_BYTES, 'hwp_stream_bytes': hwp2html.MAX_STREAM, 'hwpx_unzipped_bytes': hwpx2html.MAX_ZIP_BYTES,
                   'convert_timeout_seconds': 120, 'parallel_conversions': 3, 'hwp_cli_timeout_seconds': HWP_CLI_TIMEOUT},
        'environment': {'HWP_CLI': "off 이면 hwp-cli 를 끄고, 경로면 그 실행 파일을 쓴다", 'STORED_LAYOUT': "off 이면 PDF 에서 한컴이 저장한 줄 끊김을 따르지 않는다(기본 lines)",
                        'SPLIT_ROWS': "off 이면 큰 표 행 나눔을 끈다(기본 on)", 'SPLIT_MIN': '행 나눔 임계값 pt(기본 300)', 'KEEP_ROWS': "표 행 붙이기: span,first(기본) 또는 off",
                        'OBJ_FIX': "HWP->HWPX 에서 hwp-cli 가 뭉갠 떠 있는 개체 배치를 원본 값으로 되돌릴 종류(기본 pic,shape,tbl; pic 만이면 그림만, off 면 끔)", 'TRAIL_FIT': "off 이면 PDF 쪽 끝에서 한 줄 문단의 뒤 줄 간격을 본문 안에서 센다(기본: 글 아래끝만)", 'ALIGN_FIX': "가운데·오른쪽·아래 정렬된 떠 있는 개체를 놓을 종류(기본 page,para,paper; off 면 끄고 제자리에 흘림)"},
        'exit_codes': {'0': '성공(결과 요약 dict 를 stdout 에 출력)', '1': '실패(원인 한 줄이 stderr 에 "오류: …" 로, 사용법 오류면 사용법)'},
        'stderr_prefixes': {'경고:': '변환은 끝났지만 손실·대체가 있음(옮기지 못한 항목, hwp-cli 대신 자체 변환기 사용, 사설 영역 문자 등)', '오류:': '변환 실패'},
        'rejects': ['HWP 3.0(옛 형식)', '암호·배포용·DRM 이 걸린 HWP', '업로드 한도(100MB) 초과', '손상된 파일', 'HWPX 가 아닌 ZIP', 'HTML 태그가 없는 텍스트'],
    }


def convert(src, dst, approval=None):
    """approval: 결재선 칸 이름들(예: ('담당','검토','확인','승인')). None 이면 결재선 없음."""
    kind = detect(src)
    ext = Path(dst).suffix.lower().lstrip('.'); out = {'htm': 'html'}.get(ext, ext)
    if (kind, out) not in ROUTES: raise ValueError(f'지원하지 않는 변환: {kind} -> {out or "(출력 확장자 없음)"}')
    try:
        res = ROUTES[kind, out](str(src), str(dst), approval)
        if isinstance(res, dict): res.setdefault('engine', ENGINES.get((kind, out)))      # 화면·장부에 어떤 엔진이 썼는지 남긴다
        return res
    except (ValueError, MemoryError): raise
    except Exception as e:      # 깨진 파일을 읽다 나는 IndexError·struct.error 등을 긴 오류 목록 대신 한 줄로(원인은 __cause__ 에 남는다)
        raise ValueError(f'파일이 손상되었거나 읽을 수 없는 구조입니다 ({type(e).__name__})') from e


if __name__ == '__main__':
    args, labels = sys.argv[1:], None
    if '--capabilities' in args:
        print(json.dumps(capabilities(), ensure_ascii=False, indent=2)); sys.exit(0)
    if '--approval' in args:
        i = args.index('--approval'); labels = approval_mod.labels_from(args[i + 1]) if i + 1 < len(args) else approval_mod.DEFAULT; del args[i:i + 2]
    if len(args) != 2: sys.exit(__doc__)
    try: print(convert(args[0], args[1], labels))
    except ValueError as e: sys.exit(f'오류: {e}')
    if Path(args[1]).suffix.lower() in ('.html', '.htm'):
        left = leftover_pua(args[1])
        if left: print(f'경고: 브라우저에서 □ 로 보일 수 있는 사설 영역 문자 {len(left)}종 ({" ".join(f"U+{c:X}" for c in left[:8])})', file=sys.stderr)

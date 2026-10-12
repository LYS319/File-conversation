"""HWP / HWPX / HTML 통합 진입점. 입력 형식은 확장자가 아니라 내용(매직 바이트)으로 알아내고, 출력 형식은 출력 확장자로 정한다.
    python convert.py 입력파일 출력파일(.html | .hwpx | .pdf) [--approval 담당,검토,확인,승인]
지원: hwp->html, hwp->hwpx(hwp-cli 직접 변환, 없거나 실패하거나 결재선이면 HTML 을 거치는 자체 변환), hwpx->html, html->hwpx, 그리고 (weasyprint 가 있으면) html·hwp·hwpx->pdf.
--approval 을 주면 문서 맨 위 오른쪽에 결재선 표를 넣는다"""
import importlib.util, json, os, re, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path
import approval as approval_mod
import hwp2html, hwpx2html, html2hwpx

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
PDF_CSS = '[style*="--hd:"]{letter-spacing:calc(var(--ls,0em) + var(--hd))!important}'


_HANGUL_PAIR = re.compile('(?<=[가-힣])(?=[가-힣])')


def _keep_words(text):
    """WeasyPrint 는 word-break:keep-all 을 몰라 한글 낱말 한가운데서 줄을 꺾는다('연구개발계획서' 가 '연구' / '개발계획서' 로 갈라짐; 한컴·브라우저는 어절째 다음 줄로 보낸다).
    변환기가 낸 HTML 은 keep-all 이 기본이라, PDF 로 찍을 때만 한글 글자 사이에 WORD JOINER(U+2060: 안 보이고 PDF 글에도 안 남는다)를 끼워 어절 가운데 줄 꺾임을 막는다.
    글자 단위로 줄을 나누는 문단(word-break:break-all)·<style>·<title> 은 그대로 둔다. keep-all 을 안 쓴 외부 HTML 도 그대로 둔다."""
    if 'word-break:keep-all' not in text: return text
    out, mode = [], None        # mode: None 보통 · 'raw' <style>/<title> 안 · 'ball' break-all 문단 안
    for tok in re.split(r'(<[^>]*>)', text):
        if tok[:1] == '<':
            t = tok.lower()
            if mode is None and t.startswith(('<style', '<title')): mode = 'raw'
            elif mode == 'raw' and t.startswith(('</style', '</title')): mode = None
            elif mode is None and t.startswith('<p') and 'word-break:break-all' in t: mode = 'ball'
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


def _to_pdf(text, dst, d, keep_words=False):
    """keep_words: HTML 파일에서 바로 PDF 로 갈 때만 켠다(어절 안 끊기). HWP·HWPX 에서 바로 갈 때는 저장된 줄 끊김대로 찍어서 켜지 않는다 — 켜면 공개 108건 쪽 수 일치가 70→67 로 줄었다(인수인계 문서 2026-10-12)."""
    import weasyprint
    from weasyprint.urls import URLFetcher
    # data: 주소만 읽는다. file://·http:// 를 열면 내 컴퓨터 파일이나 내부망 주소가 새어 나갈 수 있어 막는다(막힌 자원은 빠질 뿐 변환은 계속)
    text = text.translate(HALFWIDTH_CJK)
    if keep_words: text = _keep_words(text)
    text = _TAIL.sub(_tail_spacing, text)
    doc = weasyprint.HTML(string=text, url_fetcher=URLFetcher(allowed_protocols=('data',))).render(stylesheets=[weasyprint.CSS(string=PDF_CSS)])
    doc.write_pdf(dst)
    return {'pages': len(doc.pages)}


def _to_html(conv):
    """HTML 로 내보내는 변환기에 결재선 옵션을 붙인다."""
    def run(src, dst, approval=None):
        r = conv(src, dst)
        if approval: approval_mod.add_to_file(dst, approval)
        return r
    return run


HWP_CLI_TIMEOUT = 60        # 초. 앱의 변환 제한(120초)보다 훨씬 짧게: 그림 많은 66MB 문서는 hwp-cli 88초(결과 62MB)·자체 변환 5초(0.5MB)라, 넘으면 자체 변환기로 바꿀 여유가 있어야 한다
LOSS_TEXT = {'control_removed': '컨트롤(양식 입력칸·체크박스 등)', 'opaque_control_unrepresentable': 'HWPX 로 표현 못 하는 개체'}      # hwp-cli 손실 보고서 코드 -> 사람이 읽는 말


def find_hwp_cli():
    """hwp-cli 실행 파일 경로: 환경변수 HWP_CLI -> PATH 의 hwp(컨테이너는 /usr/local/bin/hwp) -> 프로젝트 tools/hwp-cli/hwp.exe(개발용). 없으면 None."""
    p = os.environ.get('HWP_CLI')
    if p in ('off', '0'): return None      # 끄기(자체 변환기만 쓰기·비교 시험용)
    if p and Path(p).is_file(): return p
    w = shutil.which('hwp')
    if w: return w
    dev = Path(__file__).resolve().parents[2] / 'tools' / 'hwp-cli' / 'hwp.exe'
    return str(dev) if dev.is_file() else None


def _hwp_to_hwpx(src, dst, approval=None):
    """HWP -> HWPX 는 hwp-cli 가 원본 구조를 그대로 옮긴다(HTML 을 거치는 자체 변환보다 글이 빠지지 않고 쪽 수가 한컴에 가깝다: 공개 문서 25건 글 보존 100% 대 96%).
    hwp-cli 가 없거나, 실패하거나, 결재선을 넣어야 하면(HTML 에 끼우는 방식이라) 자체 변환기로 바꾼다. 손실 보고서는 '경고:' 로 알린다."""
    fallback = _via_html(hwp2html.convert, _to_hwpx)
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
        shutil.copyfile(out, dst)
        try: events = json.loads((Path(d) / 'loss.json').read_text(encoding='utf-8')).get('events', [])
        except (OSError, ValueError): events = []
        lost = [f'{LOSS_TEXT[e["code"]]} {e["count"]}개' for e in events if e.get('code') in LOSS_TEXT]
        if lost: print('경고: hwp-cli 변환에서 옮겨지지 않은 항목: ' + ', '.join(lost), file=sys.stderr)
        return {'engine': 'hwp-cli', 'bytes': Path(dst).stat().st_size}


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
    ROUTES.update({('html', 'pdf'): _via_html(None, lambda text, dst, d: _to_pdf(text, dst, d, keep_words=True)), ('hwp', 'pdf'): _via_html(_stored_pdf(hwp2html.convert), _to_pdf),
                   ('hwpx', 'pdf'): _via_html(_stored_pdf(hwpx2html.convert), _to_pdf)})


def convert(src, dst, approval=None):
    """approval: 결재선 칸 이름들(예: ('담당','검토','확인','승인')). None 이면 결재선 없음."""
    kind = detect(src)
    ext = Path(dst).suffix.lower().lstrip('.'); out = {'htm': 'html'}.get(ext, ext)
    if (kind, out) not in ROUTES: raise ValueError(f'지원하지 않는 변환: {kind} -> {out or "(출력 확장자 없음)"}')
    try: return ROUTES[kind, out](str(src), str(dst), approval)
    except (ValueError, MemoryError): raise
    except Exception as e:      # 깨진 파일을 읽다 나는 IndexError·struct.error 등을 긴 오류 목록 대신 한 줄로(원인은 __cause__ 에 남는다)
        raise ValueError(f'파일이 손상되었거나 읽을 수 없는 구조입니다 ({type(e).__name__})') from e


if __name__ == '__main__':
    args, labels = sys.argv[1:], None
    if '--approval' in args:
        i = args.index('--approval'); labels = approval_mod.labels_from(args[i + 1]) if i + 1 < len(args) else approval_mod.DEFAULT; del args[i:i + 2]
    if len(args) != 2: sys.exit(__doc__)
    try: print(convert(args[0], args[1], labels))
    except ValueError as e: sys.exit(f'오류: {e}')
    if Path(args[1]).suffix.lower() in ('.html', '.htm'):
        left = leftover_pua(args[1])
        if left: print(f'경고: 브라우저에서 □ 로 보일 수 있는 사설 영역 문자 {len(left)}종 ({" ".join(f"U+{c:X}" for c in left[:8])})', file=sys.stderr)

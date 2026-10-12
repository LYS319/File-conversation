"""HWP / HWPX / HTML 통합 진입점. 입력 형식은 확장자가 아니라 내용(매직 바이트)으로 알아내고, 출력 형식은 출력 확장자로 정한다.
    python convert.py 입력파일 출력파일(.html | .hwpx)
지원: hwp->html, hwp->hwpx(HTML을 거쳐 한 번에), hwpx->html, html->hwpx"""
import re, sys, tempfile, zipfile
from pathlib import Path
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
    if b'\0' in head: raise ValueError('알 수 없는 바이너리 형식 (HWP·HWPX·HTML 아님)')
    m = HTML_TAG.search(head)
    if not m: raise ValueError('텍스트 파일이지만 HTML 태그가 없음')
    return 'html', f'텍스트 + HTML 태그 발견({m.group(0).decode("latin-1")}…)'      # ponytail: 앞 8KB만 본다. UTF-16 HTML은 바이너리로 거부


def detect(path):
    return inspect(path)[0]


def leftover_pua(path):
    """변환된 HTML 에 남은 사설 영역 문자의 코드(글꼴에 따라 □ 로 보인다). 모르는 기호를 조용히 놓치지 않으려고 센다."""
    return sorted({ord(c) for c in PUA_RE.findall(Path(path).read_text(encoding='utf-8'))})


def _hwp_to_hwpx(src, dst):
    with tempfile.TemporaryDirectory() as d:
        mid = str(Path(d) / 'mid.html'); hwp2html.convert(src, mid)
        return html2hwpx.build(mid, dst)


def _html_to_hwpx(src, dst):
    """html2hwpx는 UTF-8만 읽는다. CP949(옛 한글 HTML)·BOM은 UTF-8로 바꿔서 넘긴다."""
    raw = Path(src).read_bytes()
    for enc in ('utf-8-sig', 'cp949'):
        try: text = raw.decode(enc); break
        except UnicodeDecodeError: pass
    else: raise ValueError('인코딩을 알 수 없는 HTML (UTF-8·CP949만 지원)')
    with tempfile.TemporaryDirectory() as d:
        mid = Path(d) / 'in.html'; mid.write_bytes(text.encode('utf-8'))      # write_text는 Windows에서 줄바꿈을 바꾼다
        return html2hwpx.build(str(mid), dst)


ROUTES = {('hwp', 'html'): hwp2html.convert, ('hwpx', 'html'): hwpx2html.convert,   # (입력 형식, 출력 형식) -> 변환 함수
          ('html', 'hwpx'): _html_to_hwpx, ('hwp', 'hwpx'): _hwp_to_hwpx}


def convert(src, dst):
    kind = detect(src)
    ext = Path(dst).suffix.lower().lstrip('.'); out = {'htm': 'html'}.get(ext, ext)
    if (kind, out) not in ROUTES: raise ValueError(f'지원하지 않는 변환: {kind} -> {out or "(출력 확장자 없음)"}')
    return ROUTES[kind, out](str(src), str(dst))


if __name__ == '__main__':
    if len(sys.argv) != 3: sys.exit(__doc__)
    try: print(convert(sys.argv[1], sys.argv[2]))
    except ValueError as e: sys.exit(f'오류: {e}')
    if Path(sys.argv[2]).suffix.lower() in ('.html', '.htm'):
        left = leftover_pua(sys.argv[2])
        if left: print(f'경고: 브라우저에서 □ 로 보일 수 있는 사설 영역 문자 {len(left)}종 ({" ".join(f"U+{c:X}" for c in left[:8])})', file=sys.stderr)

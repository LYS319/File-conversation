import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib import ROOT, snip, whole, code, esc
import diagrams as D
from style import CSS

OUT = ROOT / 'docs' / '쉬운_설명_파일변환_전체구조.html'
loc = lambda rel: len((ROOT / rel).read_text(encoding='utf-8').splitlines())


def kid(*paras, title='쉽게 말하면'):
    return f'<div class="kid"><div class="kh">🧒 {title}</div>' + ''.join(f'<p>{p}</p>' for p in paras) + '</div>'


def dgm(svg, cap=''):
    return f'<div class="dgwrap">{svg}</div>' + (f'<p class="dgcap">{cap}</p>' if cap else '')


def part(pid, title, sub, kid_html, codes_html, extra=''):
    return (f'<h3 id="{pid}">{title}<span class="sub">{sub}</span></h3>{kid_html}'
            f'<h4>💻 실제 코드와 🔍 줄별 설명</h4>{codes_html}{extra}')


def table(head, rows, cls=''):
    h = ''.join(f'<th>{c}</th>' for c in head)
    r = ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in row) + '</tr>' for row in rows)
    return f'<div class="tw"><table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{r}</tbody></table></div>'


# ======================================================================= 코드 조각 + 줄 설명
# ---- convert.py
C_INSPECT = code(snip('convert.py', 'OLE2 = bytes.fromhex', end='def detect'), [
    ('OLE2 = bytes.fromhex', 'HWP 파일의 <b>비밀 도장</b>이에요. 한글(HWP) 파일은 맨 앞 8바이트가 언제나 <code>D0 CF 11 E0 A1 B1 1A E1</code> 입니다. 이름표가 아니라 몸에 새긴 문신이라, 파일 이름을 바꿔도 속지 않아요.'),
    ('HTML_TAG = re.compile', 'HTML 태그 이름 목록(<code>&lt;html</code>, <code>&lt;body</code>, <code>&lt;table</code>, <code>&lt;p</code>, <code>&lt;div</code> …)이에요. 글자 파일 안에 이 중 하나라도 있어야 HTML 로 인정합니다. <code>re.I</code> 는 대소문자를 구분하지 않는다는 뜻.'),
    ('def inspect(path)', '<b>(형식, 판별 근거)</b> 두 가지를 돌려줘요. 근거는 화면에 “판별 근거: …” 로 그대로 보여 줍니다.'),
    ('head = f.read(8192)', '파일 맨 앞 <b>8,192바이트(8KB)만</b> 읽어요. 66MB 파일도 봉투 겉면만 보면 되니까 순식간이에요.'),
    ('head[:8] == OLE2', '앞 8바이트가 도장과 같으면 <b>HWP</b>.'),
    ('zipfile.is_zipfile(path)', 'ZIP(지퍼백)이면 그 안에 <code>mimetype</code> 파일이 있는지 열어 봐요.'),
    ("z.read('mimetype')", '그 글자가 <code>application/hwp+zip</code> 이면 <b>HWPX</b> 예요. ZIP 이라고 다 HWPX 는 아니거든요(워드 <code>.docx</code> 도 ZIP).'),
    ("raise ValueError('HWPX가 아닌 ZIP 파일')", 'ZIP 인데 HWPX 가 아니면 돌려보내요.'),
    ("b'\\0' in head", '글자 파일에는 <b>NUL(0번) 바이트</b>가 없어요. 있으면 그림·실행 파일 같은 “글이 아닌 것”이라 거절합니다.'),
    ('m = HTML_TAG.search(head)', '글자 파일이어도 HTML 태그가 <b>하나도 없으면</b> “HTML 이 아님”. 그냥 메모장 글을 HTML 로 착각하지 않게 하는 문지기예요.'),
    ("return 'html', f'텍스트", '통과! 근거와 함께 돌려줘요. (알려진 한계: 앞 8KB 만 보고, UTF-16 HTML 은 NUL 때문에 바이너리로 거절돼요.)'),
])
C_HTML = code(snip('convert.py', 'def _html_to_hwpx', end='ROUTES = {'), [
    ('def _html_to_hwpx', 'HTML→HWPX 길의 <b>앞문</b>. <code>html2hwpx.py</code> 는 UTF-8 글자만 읽을 줄 알아서, 옛날 한글 HTML(CP949)이 오면 UTF-8 로 <b>통역</b>해서 넘겨요.'),
    ("for enc in ('utf-8-sig', 'cp949')", '먼저 UTF-8(앞에 BOM 이 붙은 것 포함)로 읽어 보고, 안 되면 CP949 로 읽어요.'),
    ("raise ValueError('인코딩을 알 수 없는", '둘 다 안 되면 이유를 알려 주며 거절해요.'),
    ('mid.write_bytes', '<b>바이트로</b> 써요. <code>write_text</code> 는 Windows 에서 줄바꿈(<code>\\n</code>→<code>\\r\\n</code>)을 바꿔서 결과가 달라질 수 있어서 피했어요.'),
])
C_ROUTES = code(snip('convert.py', 'ROUTES = {', end='if __name__'), [
    ('ROUTES = {', '<b>변환 길 표</b>예요. “(입력 형식, 출력 형식)” 쌍마다 일할 함수가 하나씩 붙어 있어요. 화면(<code>app.py</code>)도 이 표를 읽어서 “고를 수 있는 형식”을 만들기 때문에, 표가 하나뿐이라 서로 어긋나지 않아요.'),
    ("('hwp', 'hwpx'): _hwp_to_hwpx", 'HWP→HWPX 는 새 변환기가 아니라 <b>“HWP→HTML 다음 HTML→HWPX”</b>를 이은 거예요(중간 HTML 은 임시 폴더에 만들었다가 지워요).'),
    ('kind = detect(src)', '먼저 입력 파일의 종류를 <b>내용으로</b> 알아내요.'),
    ('ext = Path(dst)', '출력 형식은 <b>출력 파일 이름의 확장자</b>로 정해요(<code>.htm</code> 도 html 로 취급).'),
    ('not in ROUTES', '표에 없는 길이면 “지원하지 않는 변환: hwp -> hwp” 처럼 이유와 함께 거절해요.'),
    ('return ROUTES[kind, out]', '표에서 함수를 꺼내 실행해요. 이게 접수 창구가 하는 일의 전부예요.'),
])

# ---- hwp2html.py
H_CFB = code(snip('hwp2html.py', 'class CFB:', n=6), [
    ('class CFB', 'OLE2 서랍장을 여는 열쇠예요. 보통은 <code>olefile</code> 라이브러리를 쓰는데, 여기서는 외부 도구 없이 <b>직접 만들었어요</b>(설치할 게 적어요).'),
    ('self.d = Path(path).read_bytes()', '파일 전체를 한 번에 메모리로 읽어요(최대 100MB — 아래 <code>load()</code> 에서 막아요).'),
    ("if d[:8] != bytes.fromhex", '서랍장 도장이 없으면 바로 “OLE2 파일이 아님”.'),
])
H_CHAIN = code(snip('hwp2html.py', 'def chain(self, s):', n=6), [
    ('for _ in range(len(self.fat) + 1)', '서랍 쪽지(FAT)를 따라가는 길이 <b>빙글빙글 도는 악의적인 파일</b>이 있어요. 따라갈 수 있는 횟수를 “쪽지 개수 + 1번”으로 막아 무한 반복을 막아요.'),
    ("raise ValueError('FAT 순환')", '그래도 끝나지 않으면 “순환”이라며 거절해요.'),
])
H_DEC = code(snip('hwp2html.py', 'def dec(b, force=None):', n=6), [
    ('if force is False or not', '압축이 안 된 서랍이면 그대로 돌려줘요.'),
    ('zlib.decompressobj(-15)', '압축 풀기 도구예요. <code>-15</code> 는 HWP 가 쓰는 “헤더 없는 deflate” 방식. <code>decompress(b, MAX_STREAM + 1)</code> 은 <b>“최대 512MB + 1바이트까지만 풀어 봐”</b> 라는 뜻이에요.'),
    ('if len(out) > MAX_STREAM', '풀린 크기가 512MB 를 넘으면 거절해요. 작은 파일이 풀면 수십 GB 가 되는 <b>“압축 폭탄”</b>을 막는 문이에요.'),
    ('if not d.eof', '압축 파일이 중간에 끊겼으면 오류를 내요(예전 <code>zlib.decompress</code> 와 같은 동작을 유지).'),
])
H_LOAD = code(snip('hwp2html.py', 'def load(src):', n=10), [
    ('MAX_BYTES', '파일이 100MB 를 넘으면 열지도 않고 거절해요.'),
    ('c = CFB(src)', '서랍장을 열어요.'),
    ("fh[:17] != b'HWP Document File'", '첫 서랍(<code>/FileHeader</code>)의 이름표가 “HWP Document File” 이 맞는지 확인해요.'),
    ('flags & 0b10110', '<b>깃발 확인</b>: 암호가 걸렸거나 배포용·DRM 문서면 지원하지 않아요(열 수 없는 문서를 억지로 열지 않아요).'),
    ('COMP = flags & 1', '깃발의 첫 번째 비트 = <b>압축 여부</b>. 이후 <code>dec()</code> 가 이 값을 참고해요.'),
])
H_TEXT = code(snip('hwp2html.py', 'EXT = {1, 2, 3', end='ALIGN = {0:'), [
    ('PUA = {', '한컴의 글머리 문자는 브라우저가 못 그리는 <b>“사설 영역(PUA)” 문자</b>(U+F09F 등)로 저장돼요. 이 표가 • · ▪ ➢ ✔ 같은 진짜 모양으로 바꿔 줘요. <code>hwpx2html.py</code> 도 이 표를 가져다 써요.'),
    ('def para_text(b)', '문단 본문 바이트를 글자로 바꾸는 함수예요. 2바이트씩(UTF-16) 읽어요.'),
    ('if ch < 32:', '32 보다 작은 번호는 글자가 아니라 <b>제어 문자</b>(표·그림 자리 표시, 줄바꿈, 탭 등)예요.'),
    ('if ch in EXT or ch in INL', '표·그림 같은 “확장 컨트롤”은 <b>자리 표시만 남기고 8칸을 건너뛰어요</b>(<code>i += 8</code>). 실제 내용은 따로 찾아와요.'),
    ('out.append((i, PUA.get(ch, chr(ch))))', '보통 글자는 그대로, 글머리 문자는 PUA 표로 바꿔서 담아요.'),
])
H_IMG = code(snip('hwp2html.py', 'def bindata_uri(bid):', n=9), [
    ('raw = c.read', '사진 서랍(<code>/BinData/BIN0001.bmp</code>)을 열어요.'),
    ('data = dec(raw', '압축을 풀어요(이 문서의 BMP 는 풀면 장당 약 70MB).'),
    ("Image.open(io.BytesIO(data)).convert('RGB')", 'Pillow 로 사진으로 열어요.'),
    ('im.thumbnail((1400, 1400))', '너무 크니 가로·세로 <b>최대 1400픽셀</b>로 줄여요.'),
    ("im.save(buf, 'JPEG', quality=85", 'JPEG 로 저장하고 base64 글자로 바꿔 <code>data:image/jpeg;base64,…</code> 주소로 HTML 안에 <b>아예 박아 넣어요</b> → HTML 파일 하나에 사진까지 다 들어 있어요.'),
])
H_CONV = code(snip('hwp2html.py', 'def convert(src, dst):', n=6), [
    ('load(src)', '서랍장을 열고 설계도(DocInfo)를 읽어 둬요.'),
    ('tree(records(dec(c.read', '본문 서랍(<code>/BodyText/Section0</code>)을 열어 → 압축을 풀고(<code>dec</code>) → 레코드 조각으로 쪼개고(<code>records</code>) → 부모·자식 나무로 엮어요(<code>tree</code>).'),
    ('body = render_paras', '나무의 문단을 하나씩 <code>&lt;p&gt;</code> 로, 표는 <code>&lt;table&gt;</code>, 그림은 <code>&lt;img&gt;</code> 로 바꿔요.'),
    ('first = re.sub', '첫 문단의 글을 문서 제목으로 써요. (이 뒤에 HTML 한 장을 조립해 파일로 씁니다.)'),
])

# ---- hwpx2html.py
X_LOAD = code(snip('hwpx2html.py', 'def load(path):', n=6), [
    ('zipfile.ZipFile(path)', '지퍼백을 열어요.'),
    ('if sum(i.file_size', '안에 든 파일들을 <b>풀면 모두 얼마나 될지</b> 먼저 계산해서 1GB 가 넘으면 거절해요. 정상 HWPX 는 0.5~1.2MB 라 아주 넉넉해요. (파이썬의 zipfile 은 표시된 크기까지만 읽으니 이 숫자는 속일 수 없어요.)'),
    ("etree.fromstring(z.read('Contents/header.xml'))", '“사전”(<code>header.xml</code>)을 읽어요: 글자·문단 모양 표.'),
    ('secs = sorted(', '본문 조각(<code>section0.xml</code>, <code>section1.xml</code> …)을 찾아요.'),
])
X_TEXT = code(snip('hwpx2html.py', 'def text_of(s, t):', n=11), [
    ('.translate(PUA)', '글자 속 <code>&lt; &gt; &amp;</code> 를 안전하게 바꾸고(<code>escape</code>), <code>.translate(PUA)</code> 로 한컴 글머리 문자를 진짜 • · 로 바꿔요. <b>이 한 줄이 예전의 “글머리가 네모로 보이던 문제”를 고쳤어요.</b>'),
    ("tag == 'lineBreak'", 'HWPX 의 특수 태그(줄바꿈, 고정폭 공백, 탭 …)를 HTML 로 바꿔요.'),
])
X_IMG = code(snip('hwpx2html.py', 'def picture(s, pic):', n=13), [
    ('file_size > MAX_BIN_BYTES', '그림이 100MB 를 넘으면 건너뛰어요.'),
    ("if fmt in ('jpeg', 'png', 'gif')", '작은 JPG·PNG·GIF 는 <b>원본 그대로</b> 쓰고,'),
    ('im.thumbnail((1600, 1600))', 'BMP 나 큰 파일은 <b>웹용 JPEG(최대 1600px)</b>로 줄여요.'),
])

# ---- html2hwpx.py
Y_BUILD1 = code(snip('html2hwpx.py', 'def build(src_html, out):', n=6), [
    ('src = open(src_html', 'HTML 글을 읽어요(UTF-8).'),
    ('lxml.html.document_fromstring(src)', 'lxml 로 <b>“나무” 구조</b>로 바꿔요(태그의 부모·자식 관계가 보여요).'),
    ('inline_style_rules(doc)', '<code>&lt;style&gt;</code> 안의 규칙(<code>.page{…}</code>, <code>td{…}</code>)을 각 태그의 <code>style</code> 속성으로 풀어 넣어요. 한글은 <code>&lt;style&gt;</code> 을 모르니까 “규칙”을 “직접 칠하기”로 바꾸는 거예요.'),
    ('page_setup(src)', '<code>@page</code> 에서 종이 크기·여백·쪽 번호를 읽어요.'),
])
Y_BUILD2 = code(snip('html2hwpx.py', 'b = Builder(); b.content_w', n=7), [
    ('b = Builder()', '<b>Builder = 한글 부품 조립 담당</b>. 글자 모양·문단 모양·테두리를 <b>번호를 매겨</b> 모아 둬요.'),
    ('paras = b.blocks(root', 'HTML 나무를 위에서 아래로 훑으며 문단(<code>hp:p</code>)·표(<code>hp:tbl</code>)·그림(<code>hp:pic</code>) XML 로 바꿔요.'),
    ("section = f'<?xml", '그 문단들을 한 장의 <code>section0.xml</code> 로 묶어요.'),
])
Y_ZIP = code(snip('html2hwpx.py', "with zipfile.ZipFile(out, 'w') as z:", n=10), [
    ("zipfile.ZipFile(out, 'w')", '지퍼백을 만들어요.'),
    ("z.writestr(zipfile.ZipInfo('mimetype')", '맨 앞에 <code>mimetype</code> 을 <b>압축 없이</b> 넣어요. 한글은 이 규칙(첫 번째·무압축)을 지켜야 HWPX 로 인식해요.'),
    ("z.writestr('Contents/header.xml'", '사전(<code>header.xml</code>), 글(<code>section0.xml</code>), 미리보기, 설정 파일 등을 차례로 넣어요.'),
    ('for n, data, _ in b.bins', '사진은 <code>BinData/</code> 폴더에 원본 그대로(JPG·PNG 는 압축 없이) 저장해요.'),
])
Y_LEN = code(snip('html2hwpx.py', 'def length(v, base_pt=None):', n=9), [
    ('CSS length -> HWPUNIT', 'HTML 은 길이를 pt·px·mm 로, 한글은 <b>HWPUNIT</b>(1pt=100, 1px=75)이라는 자기 단위로 재요. 이 함수가 <b>통역</b>해요.'),
    ("f = {'pt':100", 'pt=100, px=75, mm≈283, cm≈2835, in=7200. 한글 단위 환산표예요.'),
])
Y_IMG = code(snip('html2hwpx.py', 'def img_size(s, img, css, ref):', n=15), [
    ('if not m: return None', '<code>data:image/…;base64</code> 로 박힌 그림만 받아요. <b>인터넷 주소(http)나 내 컴퓨터 경로는 읽지 않아요</b> → 남의 서버·내 파일을 몰래 읽게 하는 공격(SSRF)을 막아요.'),
    ('if len(data) > MAX_IMG_BYTES', '100MB 넘는 그림은 거절해요.'),
    ('if pw * ph > 100_000_000', '1억 화소를 넘는 그림(풀면 메모리를 다 먹는 “그림 폭탄”)도 거절해요.'),
    ('if w > ref', '칸 폭보다 크면 <b>비율을 지켜 줄여요</b> — 그림이 칸 밖으로 삐져나가지 않게.'),
])
Y_EST = code(snip('html2hwpx.py', 'def est_height(td, w, img_h=None):', n=8), [
    ('높이 지정이 없는 셀', '표 칸에 높이가 안 적혀 있으면 <b>글 양을 보고 필요한 높이를 “어림”</b>해요. 안 넣으면 일부 프로그램이 칸을 잘라 버려서요. 한컴 원본 값과 3% 안쪽으로 맞췄어요.'),
    ('total = 283', '위아래 안쪽 여백부터 시작해서,'),
    ("for p in td.xpath('.//p')", '칸 안의 문단마다 글자 수·글자 크기·줄 간격으로 줄 수를 어림해 더해요.'),
])

# ---- app.py
A_CONST = code(snip('app.py', 'TIMEOUT = 120', end='@st.cache_data'), [
    ('TIMEOUT = 120', '변환 한 건이 <b>120초</b>를 넘으면 강제 종료해요. 가장 큰 샘플(66MB)이 2~3초라 아주 넉넉해요.'),
    ('MAX_PARALLEL = 3', '동시에 변환할 수 있는 건 <b>3개</b>. 공장 작업대가 3개라고 생각하세요.'),
    ('WAIT = 60', '작업대가 다 찼으면 <b>60초까지</b> 기다려요.'),
    ('class Busy', '“지금 바빠요” 를 뜻하는 신호(예외)예요.'),
    ('@st.cache_resource', 'Streamlit 은 버튼을 누를 때마다 파일을 <b>처음부터 다시 실행</b>해요. 그냥 변수로 두면 매번 새로 만들어지죠. <code>cache_resource</code> 는 “모든 사용자가 같은 것을 공유”하게 해 줘요.'),
    ('threading.BoundedSemaphore', '<b>세마포어 = 번호표 3장</b>. 변환을 시작하려면 한 장 가져가고(<code>acquire</code>), 끝나면 반납(<code>release</code>)해요. 3장이 다 나가면 다음 사람은 기다려요.'),
])
A_INSPECT = code(snip('app.py', 'def inspect_upload(data):', n=5), [
    ('tempfile.TemporaryDirectory()', '임시 폴더를 만들어 파일을 잠깐 써요. <code>with</code> 블록이 끝나면 폴더째 사라져요.'),
    ('convert.inspect(p)', '접수 창구에게 종류를 물어봐요. 같은 파일이면 결과를 기억(<code>cache_data</code>)해서 다시 묻지 않아요.'),
])
A_RUN = code(snip('app.py', 'def run(data, target):', n=15), [
    ('if not slots().acquire(timeout=WAIT)', '번호표를 받아요. 60초를 기다려도 없으면 <code>Busy</code>.'),
    ('subprocess.run([sys.executable', '<code>convert.py</code> 를 <b>별도 프로그램</b>으로 실행해요. 같은 곳에서 직접 부르지 않는 이유: ① <code>hwp2html</code> 이 “프로세스당 한 건”만 전제로 짜여 있어 동시 접속이 섞이면 안 되고, ② 멈추거나 터져도 화면은 안 죽고, ③ 시간 제한을 걸 수 있어요.'),
    ('timeout=TIMEOUT', '120초 제한. 넘으면 파이썬이 그 프로세스를 죽이고 <code>TimeoutExpired</code> 를 던져요.'),
    ('if r.returncode: raise RuntimeError', '<code>convert.py</code> 가 오류로 끝났으면 마지막 오류 줄을 화면용 메시지로 써요.'),
    ('warn = next(', '변환이 <b>성공했어도</b> <code>convert.py</code> 가 적어 둔 “경고:” 줄이 있으면 가져와요(예: 브라우저에서 □ 로 보일 수 있는 사설 영역 문자). 화면에 노란 경고로 보여 줘요.'),
    ('finally:', '무슨 일이 있어도 번호표는 <b>반납</b>해요. 안 하면 자리가 영영 줄어요.'),
])
A_LOG = code(snip('app.py', 'def convert_logged(data, kind, target):', n=11), [
    ('except Busy', '세 가지 실패를 사람이 읽는 말로 바꿔요: 바쁨, 시간 초과, 변환 실패.'),
    ('log(kind=kind', '성공이든 실패든 <b>장부에 한 줄</b>. 파일 이름·본문은 쓰지 않고, 입력의 <b>해시(지문) 앞 16자리</b>만 남겨요 — 같은 파일인지는 알 수 있지만 내용은 알 수 없어요.'),
])
A_MAIN = code(snip('app.py', 'def main():', end='if __name__'), [
    ('up = st.file_uploader', '파일을 올리는 상자예요. 올리면 아래 줄들이 실행돼요.'),
    ('if up is None: st.stop()', '아직 안 올렸으면 여기서 멈춰요.'),
    ('kind, why = inspect_upload(data)', '종류와 근거를 알아내요. 못 알아내면 이유를 보여 주고 멈춰요.'),
    ('st.caption', '“판별 근거: …” 한 줄을 보여 줘요.'),
    ('target = st.radio', '가능한 변환 길만 보여 줘요(<code>ROUTES</code> 표에서). HWPX 를 올리면 HTML 하나뿐이에요.'),
    ("if st.button('변환'", '버튼을 눌렀을 때만 변환해요.'),
    ("st.session_state['result']", '결과는 <b>“세션 기억”</b>에 보관해요. 다운로드 버튼을 눌러도 화면이 다시 실행되는데, 그때 결과가 사라지면 안 되니까요.'),
    ('st.download_button', '내려받기 버튼.'),
])

# ---- Docker
DK = code(whole('Dockerfile'), [
    ('FROM python:3.12-slim', '가볍게 줄인 파이썬 3.12 가 든 빈 방에서 시작해요.'),
    ('ENV PYTHONDONTWRITEBYTECODE=1', '파일시스템이 읽기 전용이라 파이썬이 <code>.pyc</code> 를 못 쓰게 끄고, <code>HOME</code> 은 쓸 수 있는 <code>/tmp</code> 로 정해요.'),
    ('RUN pip install', '꼭 필요한 3개(streamlit, lxml, pillow)만, 시험한 버전으로 <b>고정</b>해서 설치해요.'),
    ('COPY app.py', '<b>코드 5개만</b> 복사해요. 다른 건 <code>.dockerignore</code> 가 막아요.'),
    ('RUN useradd', '관리자가 아닌 <b>일반 사용자(app)</b>를 만들고, 그 이름으로 실행(<code>USER app</code>)해요.'),
    ('CMD ["streamlit"', '시작 명령이에요. 컨테이너 안에서는 <code>0.0.0.0</code> 으로 열어야 밖에서 닿아요. 진짜 문단속은 <code>compose.yaml</code> 의 <code>127.0.0.1</code> 이 해요.'),
], lang='hash')
DC = code(whole('compose.yaml'), [
    ('127.0.0.1:8501:8501', '내 PC 의 127.0.0.1(자기 자신) 8501 번만 컨테이너로 이어요. <b><code>127.0.0.1:</code> 을 빼면 같은 네트워크의 누구나 접속</b>할 수 있게 돼요.'),
    ('restart: unless-stopped', '죽거나 Docker 가 다시 켜지면 자동으로 다시 시작해요. 내가 멈추면 그대로 멈춰 있어요.'),
    ('read_only: true', '컨테이너 파일시스템을 <b>읽기 전용</b>으로. 뚫려도 파일을 못 바꿔요.'),
    ('/tmp:size=1g', '임시 파일은 <b>메모리 위의 1GB 칸</b>(tmpfs)에만 써요. 메모리 한도에도 포함돼요.'),
    ('./logs:/app/logs', '장부 폴더만 내 PC 폴더와 <b>공유</b>(bind mount)해요.'),
    ('cap_drop: [ALL]', '리눅스 특수 권한을 전부 반납해요.'),
    ('no-new-privileges', '프로그램이 몰래 권한을 올리는 것을 금지해요.'),
    ('mem_limit: 3g', '메모리 <b>3GB 상한</b>(66MB 변환 8개 동시 시험에서 최대 1.5GB 를 썼어요).'),
    ('healthcheck:', '30초마다 “살아 있나?”를 확인해요(<code>/_stcore/health</code>).'),
], lang='hash')
DI = code(whole('.dockerignore'), [
    ('*', '일단 <b>“전부 제외”</b>. 그다음 <code>!</code> 로 시작하는 줄만 예외로 허용해요.'),
    ('!app.py', '<b>허용 목록</b>이에요. 여기 적힌 파일만 포장 상자에 들어가요. <code>.env</code>(API 키), <code>langfuse/</code>, <code>samples/</code> 는 자동으로 빠지니 실수로 비밀이 들어갈 수 없어요.'),
], lang='hash')
DT = code(whole('.streamlit/config.toml'), [
    ('maxUploadSize', '올릴 수 있는 최대 크기 <b>100MB</b>. <code>hwp2html</code> 의 입력 상한과 맞췄어요(기본 200MB 면 다 올린 뒤에야 거절돼요).'),
    ('address = "localhost"', '이 PC 에서만 접속해요(컨테이너 안에서는 실행 명령의 옵션이 이 값을 덮어써요).'),
    ('gatherUsageStats', '사용 통계를 밖으로 보내지 않아요.'),
], lang='hash')

# ---- 테스트
T_DEF = code(snip('test_hwpx_roundtrip.py', '# 입력 방어', n=15), [
    ("try: convert.detect(tmp / 'n.txt')", '메모장 같은 글이 HTML 로 통과하면 안 돼요(통과하면 시험 <b>실패</b>).'),
    ("kind, why = convert.inspect(tmp / 'k.html')", '옛 한글 인코딩(CP949) HTML 도 HTML 로 알아봐요.'),
    ("assert '안녕회의록'", '변환한 HWPX 를 열어 <b>글자가 그대로인지</b> 확인해요.'),
    ('setattr(mod, name, 1000)', '진짜 1GB 파일을 만들 수는 없으니 한도를 <b>1000바이트로 낮춰</b> “한도 문이 실제로 닫히는지” 확인하고(<code>finally</code>), 원래 값으로 되돌려요.'),
])

# ======================================================================= 페이지
files = [('app.py', '안내 데스크(웹 화면)', '브라우저'), ('convert.py', '접수 창구(형식 판별 + 변환 길 표)', 'app.py · 터미널'),
         ('hwp2html.py', '번역가 1: HWP → HTML', 'convert.py · hwpx2html.py(글머리 표)'),
         ('hwpx2html.py', '번역가 2: HWPX → HTML', 'convert.py'), ('html2hwpx.py', '번역가 3: HTML → HWPX', 'convert.py'),
         ('test_hwpx_roundtrip.py', '점검표(회귀 테스트)', '사람이 실행')]
frows = [[f'<code>{f}</code>', d, f'{loc(f):,}줄', u] for f, d, u in files]

parts_html = []
# ---- 0. 읽는 법 + 1. 이야기
parts_html.append(f'''
<header class="hero" id="top">
  <h1>📦 파일 변환 공장 이야기</h1>
  <p>HWP · HWPX · HTML 사이를 오가는 변환기가 어떻게 생겼고 어떻게 돌아가는지를, <b>쉬운 말 → 실제 코드 → 줄별 설명</b> 순서로 풀어 쓴 문서예요. 코드는 지금 프로젝트의 실제 파일에서 그대로 가져왔어요.</p>
  <div class="chips">
    <span class="chip">입력 형식 <b>3</b>종</span><span class="chip">변환 길 <b>4</b>개</span><span class="chip">안전 문 <b>6</b>개</span>
    <span class="chip">66MB 회의록 <b>2.3초</b></span><span class="chip">기준일 <b>2026-10-07</b></span>
  </div>
</header>

<section id="s0"><h2><span class="num">0</span>이 문서 읽는 법</h2>
<div class="cards">
  <div class="cardx"><div class="em">🧒</div><h5>쉽게 말하면</h5><p>노란 상자. 어린이도 이해하도록 비유로 설명해요.</p></div>
  <div class="cardx"><div class="em">💻</div><h5>실제 코드</h5><p>검은 상자. 파일에서 그대로 뽑았고, 왼쪽 숫자는 <b>실제 파일의 줄 번호</b>예요.</p></div>
  <div class="cardx"><div class="em">🔍</div><h5>줄별 설명</h5><p>코드의 노란 <b>①②③ 배지</b>가 붙은 줄과, 코드 아래 설명 번호가 짝이에요.</p></div>
</div>
<div class="tip">코드 상자는 복사해도 줄 번호와 배지는 따라오지 않아요. 도식이 작게 보이면 옆으로 밀어 보세요(휴대폰).</div>
</section>

<section id="s1"><h2><span class="num">1</span>이야기로 먼저 이해하기</h2>
{kid("편지 한 통을 떠올려 보세요. 편지 안에는 <b>글자, 그림, 표</b>가 들어 있어요. 그런데 이 편지를 담는 통이 세 가지가 있어요. 통마다 모양도 다르고 여는 방법도 달라요.",
     "이 프로그램은 <b>편지 내용은 그대로 두고, 담는 통만 바꿔 주는 공장</b>이에요. 서랍장에 든 편지를 꺼내 투명 비닐로, 비닐에서 지퍼백으로 옮겨 담는 거죠.")}
<div class="cards">
  <div class="cardx"><div class="em">🗄️</div><h5>HWP (.hwp)</h5><p>옛날 한글 프로그램의 <b>잠긴 서랍장</b>. 서랍마다 이름이 붙어 있어요(이름표·설계도·본문·사진). 서랍 안은 꾹꾹 눌러 담아서(압축) 열려면 서랍장 설계 방법을 알아야 해요.</p></div>
  <div class="cardx"><div class="em">🛍️</div><h5>HWPX (.hwpx)</h5><p>새 한글의 <b>지퍼백</b>. 지퍼를 열면(ZIP) 글로 쓴 설명서(XML) 파일들이 폴더에 들어 있어요. 사람이 열어 읽을 수 있어요.</p></div>
  <div class="cardx"><div class="em">🌐</div><h5>HTML (.html)</h5><p>인터넷 브라우저가 바로 보여 주는 <b>투명 비닐</b>. 글, 표, 사진이 한눈에 보여요. 변환의 “중간 정거장”으로도 써요.</p></div>
</div>
<h4>공장에 사는 식구들</h4>
{table(["이름","어디에 있나","하는 일 (비유)"],[
  ["📣 안내 데스크","<code>app.py</code>","손님(브라우저)이 파일을 내밀면 받아서 접수 창구에 넘기고, 결과를 돌려줘요."],
  ["🛎️ 접수 창구","<code>convert.py</code>","파일 겉을 보고 “이건 HWP 네” 하고 알아낸 뒤, 알맞은 번역가를 불러요."],
  ["🧑‍🔧 번역가 1","<code>hwp2html.py</code>","서랍장(HWP)을 열어 내용을 꺼내 비닐(HTML)에 옮겨요."],
  ["🧑‍🔧 번역가 2","<code>hwpx2html.py</code>","지퍼백(HWPX)을 열어 내용을 비닐(HTML)에 옮겨요."],
  ["🧑‍🔧 번역가 3","<code>html2hwpx.py</code>","비닐(HTML) 내용을 새 지퍼백(HWPX)으로 조립해요."],
  ["💂 경비 아저씨","코드 곳곳","너무 크거나 이상한 파일은 문 앞에서 돌려보내요(6가지 문)."],
  ["📒 장부","<code>logs/requests.jsonl</code>","누가 뭘 얼마나 걸려 바꿨는지 한 줄씩 적어요(파일 이름·내용은 안 적어요)."],
  ["🫙 유리 공장","<code>Dockerfile</code> · <code>compose.yaml</code>","공장 전체를 유리 상자 안에 넣어 두고, 상자 밖과는 작은 구멍 하나로만 이어요."],
  ["✅ 점검표","<code>test_hwpx_roundtrip.py</code>","고친 뒤에도 옛날 결과가 그대로인지 한 번에 확인해요."],
])}
</section>
''')

# ---- 2. 흐름 / 3. 상세 구조도
parts_html.append(f'''
<section id="s2"><h2><span class="num">2</span>지금 흐름 — 한눈에</h2>
{kid("손님이 안내 데스크에 파일을 내밀면, 안내 데스크는 접수 창구에 “이거 바꿔 주세요” 하고 <b>따로 일하는 직원(새 프로그램)</b>을 불러요. 그 직원이 알맞은 번역가를 찾아 일을 시키고, 결과를 안내 데스크에 돌려줘요. 안내 데스크는 장부에 한 줄 적고 손님에게 내려받기 버튼을 보여 줘요.")}
{dgm(D.flow(), "그림 1. 전체 흐름. 실선은 호출·전달, 왼쪽의 긴 화살표는 결과가 돌아오는 길이에요. ①⑦⑩⑪⑫ 번호는 바로 아래 3장 상세 구조도의 12단계 번호와 같아요.")}
<h4>버튼 한 번 누르면 벌어지는 일 (요약)</h4>
<ol class="step">
  <li><b>파일 올리기</b> — 100MB 이하만 올라가요(<code>.streamlit/config.toml</code>).</li>
  <li><b>종류 알아내기</b> — 파일 맨 앞 8KB 를 보고 HWP/HWPX/HTML 을 판별하고, 근거를 화면에 보여 줘요.</li>
  <li><b>가능한 길만 보여 주기</b> — 변환 길 표(<code>ROUTES</code>)에 있는 출력 형식만 고를 수 있어요.</li>
  <li><b>자리 잡기</b> — 동시에 3개까지만. 다 찼으면 60초까지 기다려요.</li>
  <li><b>새 프로그램으로 변환</b> — 임시 폴더에 파일을 쓰고 <code>convert.py</code> 를 따로 실행해요(120초 제한).</li>
  <li><b>번역가가 일하기</b> — 압축 폭탄·그림 폭탄 같은 위험을 확인하며 변환해요.</li>
  <li><b>결과 돌려받기·장부 쓰기</b> — 결과를 읽고 임시 폴더를 지운 뒤, 성공·실패 모두 장부에 한 줄 적어요.</li>
  <li><b>내려받기</b> — 결과 크기와 걸린 시간을 보여 주고 내려받기 버튼을 줘요.</li>
</ol>
</section>

<section id="s3"><h2><span class="num">3</span>상세 구조도 — 요청 한 건의 12단계</h2>
{kid("아래 그림은 같은 일을 <b>누가 누구에게 무엇을 시키는지</b> 시간 순서로 그린 거예요. 위에서 아래로 읽어요. 점선 화살표는 “대답”이에요.")}
{dgm(D.sequence(), "그림 2. 요청 1건의 순서도. 세로 점선은 각자의 “시간 줄”이고, 위에서 아래로 시간이 흘러요.")}
{table(["단계","누가 · 어떤 코드","설명"],[
  ["①","브라우저 → <code>app.py</code>","<code>st.file_uploader</code>. 100MB 넘으면 올리자마자 거절돼요."],
  ["②","<code>inspect_upload()</code> → <code>convert.inspect()</code>","임시 파일로 써서 맨 앞 8KB 로 판별. 같은 파일이면 결과를 기억해 둬요."],
  ["③","<code>st.info</code> · <code>st.caption</code> · <code>st.radio</code>","판별 결과·근거·고를 수 있는 변환 형식을 보여 줘요."],
  ["④","<code>st.button('변환')</code>","버튼을 누르면 화면 코드가 처음부터 다시 실행되고, 이번엔 버튼 안쪽이 실행돼요."],
  ["⑤","<code>slots().acquire(timeout=60)</code>","번호표 3장 중 하나. 없으면 60초 후 <code>Busy</code>."],
  ["⑥","<code>run()</code>","임시 폴더에 <code>input</code> 파일을 써요."],
  ["⑦","<code>subprocess.run([python, convert.py, …])</code>","새 프로세스. 120초를 넘으면 강제 종료."],
  ["⑧","<code>convert.convert()</code> → <code>ROUTES[…]</code>","다시 종류를 알아내고 표에서 변환 함수를 꺼내 실행해요."],
  ["⑨","변환기 → 디스크","결과를 <code>output.hwpx</code>/<code>.html</code> 로 써요. 이 과정에서 압축 한도·그림 한도를 확인해요."],
  ["⑩","<code>convert.py</code> → <code>app.py</code>","종료 코드 0 이면 성공. 아니면 마지막 오류 줄을 가져와 <code>RuntimeError</code> 로."],
  ["⑪","<code>run()</code> · <code>convert_logged()</code>","결과를 읽고, 임시 폴더를 지우고, 번호표를 반납하고, 장부에 한 줄 써요."],
  ["⑫","<code>st.success</code> · <code>st.download_button</code>","결과를 세션에 보관하고 내려받기 버튼을 보여 줘요."],
])}
</section>
''')

# ---- 4. 변환 길 / 5. 파일 지도
parts_html.append(f'''
<section id="s4"><h2><span class="num">4</span>변환 길 지도</h2>
{kid("HWP, HTML, HWPX 는 세 도시예요. 도시 사이에 <b>길(번역가)</b>이 놓여 있어요. 지금 놓인 길은 4개예요. 길이 없는 곳으로 가자고 하면 “그 길은 없어요” 하고 돌려보내요.")}
{dgm(D.routes(), "그림 3. 변환 길. HWP→HWPX 는 새 길이 아니라 위쪽 두 길을 이은 지름길이에요.")}
{table(["입력 → 출력","누가 일하나","핵심 일"],[
  ["HWP → HTML","<code>hwp2html.py</code>","서랍장 열기 → 압축 풀기 → 글·표·그림을 HTML 로. 사진은 JPEG 로 줄여 HTML 안에 박아요."],
  ["HWPX → HTML","<code>hwpx2html.py</code>","지퍼백 열기 → 사전(header.xml)의 모양표로 글(section0.xml)을 꾸며 HTML 로."],
  ["HTML → HWPX","<code>html2hwpx.py</code> (앞문: <code>_html_to_hwpx</code>)","HTML 규칙을 풀어 한글 단위로 통역하고, 번호 붙인 사전과 글을 조립해 지퍼백으로."],
  ["HWP → HWPX","<code>_hwp_to_hwpx</code>","위 1번 다음 3번을 이어서 한 번에(중간 HTML 은 임시 폴더에서 지워요)."],
])}
</section>

<section id="s5"><h2><span class="num">5</span>파일 지도 — 누가 누구를 부르나</h2>
{dgm(D.filemap(), "그림 4. 실선은 “부른다”, 점선은 “가져다 쓴다/확인한다/포장한다”예요.")}
{table(["파일","역할","크기","누가 부르나"], frows)}
<div class="tip">변환기 3개는 서로 거의 독립이에요. 유일한 연결은 <code>hwpx2html.py</code> 가 <code>hwp2html.py</code> 의 글머리 표(<code>PUA</code>)를 빌려 쓰는 것 하나예요. 그래서 이 파일들은 <b>같은 폴더</b>에 있어야 해요.</div>
</section>
''')

# ---- 6. 코드 읽기
parts_html.append('<section id="s6"><h2><span class="num">6</span>부품별로 코드 읽기</h2><p>순서: 접수 창구 → 번역가 3명 → 안내 데스크. 번역가 파트에는 “파일 안이 어떻게 생겼는지” 그림도 있어요.</p>')

parts_html.append(part('p-convert', '🛎️ convert.py', '접수 창구 · '+f'{loc("convert.py")}줄',
    kid('손님이 가져온 파일의 <b>겉</b>을 봅니다. 봉투에 “HWP”라고 써 있어도 믿지 않고, <b>몸에 새겨진 도장</b>을 확인해요. 도장이 있으면 알맞은 번역가에게, 없으면 이유를 말하며 돌려보내요.',
        '그리고 <b>길 표(ROUTES)</b> 하나로 “이 파일은 이 번역가에게” 를 정해요. 화면도 이 표를 읽으니까, 새 길을 만들 때 표에 한 줄만 더하면 화면에도 자동으로 나타나요.'),
    '<h4>① 형식 판별 inspect()</h4>' + C_INSPECT + '<h4>② HTML 입구 — 옛 한글 인코딩 통역</h4>' + C_HTML + '<h4>③ 변환 길 표와 convert()</h4>' + C_ROUTES))

parts_html.append(part('p-hwp', '🧑‍🔧 hwp2html.py', '번역가 1: HWP → HTML · '+f'{loc("hwp2html.py")}줄',
    kid('HWP 는 <b>잠긴 서랍장</b>이에요. 서랍장 안에는 이름이 붙은 서랍이 있고(<b>이름표</b>, <b>설계도</b>, <b>본문</b>, <b>사진</b>), 서랍마다 꾹꾹 눌러 담겨(압축) 있어요.',
        '번역가는 ① 서랍장 도장을 확인하고 ② 이름표의 깃발(압축? 암호?)을 보고 ③ 설계도에서 글자 모양을 알아내고 ④ 본문 서랍을 펴서 글·표·그림 자리를 하나씩 HTML 로 옮겨요. 사진은 너무 크니 줄여서 HTML 안에 아예 박아 넣어요.'),
    dgm(D.hwp_inside(), '그림 5. HWP 파일 안. 서랍 4개와, 각 서랍을 읽는 함수예요.')
    + '<h4>서랍장 열기 — CFB 클래스</h4>' + H_CFB + H_CHAIN
    + '<h4>압축 풀기와 압축 폭탄 방어 — dec()</h4>' + H_DEC
    + '<h4>이름표·깃발 확인과 설계도 읽기 — load()</h4>' + H_LOAD
    + '<h4>글자 읽기와 글머리 바꾸기 — para_text()</h4>' + H_TEXT
    + '<h4>사진 꺼내 줄이기 — bindata_uri()</h4>' + H_IMG
    + '<h4>전체를 묶는 convert()</h4>' + H_CONV,
    '<div class="warn"><b>알려진 한계.</b> 이 파일은 “그 문서 한 건에 맞춘 프로토타입”이라고 코드 머리말에 적혀 있어요. 첫 구역(Section0)만 읽고, 머리글·바닥글·쪽 설정은 아직 없고, 표 테두리와 폭은 단순화해요. 샘플 2건에서만 확인했어요.</div>'))

parts_html.append(part('p-hwpx2html', '🧑‍🔧 hwpx2html.py', '번역가 2: HWPX → HTML · '+f'{loc("hwpx2html.py")}줄',
    kid('HWPX 는 <b>지퍼백</b>이에요. 지퍼를 열면 <b>사전(header.xml)</b>과 <b>글(section0.xml)</b>이 들어 있어요. 글에는 “3번 모양으로 써 주세요” 처럼 <b>번호</b>만 적혀 있고, 3번이 뭔지는 사전에 있어요.',
        '번역가는 사전의 모양표를 먼저 읽어 두고, 글을 한 문단씩 읽으면서 번호를 모양(글꼴·크기·색·정렬)으로 바꿔 HTML 에 적어요. 표는 칸마다 폭·높이·테두리·배경을 옮기고, 그림은 웹용으로 줄여 박아 넣어요.'),
    dgm(D.hwpx_inside(), '그림 6. HWPX 지퍼백 안. 글(section0)의 번호가 사전(header)을 가리켜요.')
    + '<h4>지퍼 열기와 압축 폭탄 방어 — load()</h4>' + X_LOAD
    + '<h4>글자 옮기기와 글머리 고치기 — text_of()</h4>' + X_TEXT
    + '<h4>그림 옮기기 — picture()</h4>' + X_IMG))

parts_html.append(part('p-html2hwpx', '🧑‍🔧 html2hwpx.py', '번역가 3: HTML → HWPX · '+f'{loc("html2hwpx.py")}줄',
    kid('가장 손이 많이 가는 번역가예요. HTML 은 “이 글은 파란색, 큰 글씨” 처럼 <b>직접 칠한 모양</b>이 곳곳에 있는데, 한글(HWPX)은 <b>모양 사전에 번호를 매겨</b> 두고 글이 번호를 가리켜야 해요.',
        '그래서 번역가는 ① HTML 의 <code>&lt;style&gt;</code> 규칙을 각 글에 직접 칠하기로 풀고 ② 길이를 한글 단위(HWPUNIT)로 통역하고 ③ 모양마다 번호를 매겨 사전(header.xml)을 만들고 ④ 글(section0.xml)이 그 번호를 가리키게 쓰고 ⑤ 사진을 BinData 에 넣고 ⑥ 모두 ZIP 으로 묶어요.'),
    '<h4>큰 줄기 — build()</h4>' + Y_BUILD1 + Y_BUILD2
    + '<h4>마지막 포장 — ZIP 쓰기</h4>' + Y_ZIP
    + '<h4>길이 통역 — length()</h4>' + Y_LEN
    + '<h4>그림 받기와 그림 폭탄 방어 — img_size()</h4>' + Y_IMG
    + '<h4>표 칸 높이 어림 — est_height()</h4>' + Y_EST))

parts_html.append(part('p-app', '📣 app.py', '안내 데스크(웹 화면) · '+f'{loc("app.py")}줄',
    kid('손님을 맞이하는 곳이에요. 파일을 받아 종류를 알려 주고, 어떤 통으로 바꿀지 고르게 하고, 버튼을 누르면 <b>작업대(번호표 3장)</b>에서 일할 직원을 불러요. 일이 끝나면 결과를 건네고 <b>장부</b>에 적어요.',
        'Streamlit 은 <b>버튼을 누를 때마다 이 파일을 처음부터 다시 읽어요</b>. 그래서 “기억해야 할 것”(번호표, 결과)은 특별한 보관함(<code>cache_resource</code>, <code>session_state</code>)에 넣어요.'),
    '<h4>상수와 번호표(세마포어)</h4>' + A_CONST + '<h4>종류 알아내기 — inspect_upload()</h4>' + A_INSPECT
    + '<h4>직원 부르기 — run()</h4>' + A_RUN + '<h4>장부 쓰기 — convert_logged()</h4>' + A_LOG
    + '<h4>화면 — main()</h4>' + A_MAIN))
parts_html.append('</section>')

# ---- 7. 안전 문 / 8. Docker / 9. 점검표 / 10. 폴더
parts_html.append(f'''
<section id="s7"><h2><span class="num">7</span>안전 문 6개 — 경비 아저씨 총정리</h2>
{kid("이상한 파일이 들어오면 큰일이니까 문을 여러 개 만들어 뒀어요. 어느 문에서든 걸리면 <b>이유를 말해 주고 돌려보내요</b>. 정상 문서는 한 번도 안 걸리게 숫자를 넉넉하게 잡았어요.")}
{dgm(D.gates(), "그림 7. 안전 문 순서. 숫자는 지금 있는 샘플을 재 보고 정한 값이에요.")}
{table(["문","어디서","기준값","왜 이 값인가","막는 것"],[
  ["① 업로드","<code>.streamlit/config.toml</code>","100MB","<code>hwp2html</code> 의 입력 상한과 맞춤. 가진 최대 파일은 63.6MB","너무 큰 파일"],
  ["② 종류 확인","<code>convert.inspect()</code>","앞 8KB 확인","도장·mimetype·HTML 태그","exe, 압축 아닌 ZIP, 태그 없는 글"],
  ["③ 자리","<code>app.py</code> slots()","3개 · 60초","66MB 변환 1건 메모리 약 390MB → 3개면 1.2GB 안팎","동시 요청 폭주"],
  ["④ 시간","<code>app.py</code> run()","120초","가장 큰 샘플이 2~3초","멈춘 변환이 자리를 오래 잡는 것"],
  ["⑤ 압축 풀기","<code>dec()</code> · <code>load()</code>","512MB / 1GB","BMP 사진이 장당 70MB, 정상 HWPX 는 약 1MB","압축 폭탄"],
  ["⑥ 그림","<code>img_size()</code> · <code>picture()</code>","100MB · 1억 화소","웹용으로 줄일 수 있는 수준","그림 폭탄, 외부 주소로 새는 것"],
])}
<div class="tip"><b>왜 HWP 압축 한도가 100MB 가 아니라 512MB 일까요?</b> 이 프로젝트의 대표 샘플(회의록)에 BMP 사진 2장이 있는데, 압축을 풀면 장당 약 70MB(5712×4284, 24비트)예요. 한도를 100MB 로 잡았다면 정상 문서가 거절됐을 거예요.</div>
</section>

<section id="s8"><h2><span class="num">8</span>Docker — 유리 상자 안의 공장</h2>
{kid("공장 전체를 <b>유리 상자(컨테이너)</b> 안에 넣어 뒀어요. 상자 안에서는 관리자 권한이 없고, 바닥(파일시스템)은 잠겨 있고, 쓸 수 있는 칸은 임시칸과 장부 폴더뿐이에요. 상자 밖과는 <b>구멍 하나(127.0.0.1:8501)</b>로만 이어져요 — 그것도 <b>이 PC 안에서만</b> 닿아요.")}
{dgm(D.docker(), "그림 8. Docker 구조. 같은 네트워크의 다른 PC 는 구멍에 닿지 못해요.")}
<p>사용: <code>docker compose up -d --build</code> → <code>http://localhost:8501</code> · 끌 때: <code>docker compose down</code></p>
<h4>Dockerfile — 상자 만드는 설명서</h4>{DK}
<h4>compose.yaml — 상자 실행 설정</h4>{DC}
<h4>.dockerignore — 상자에 넣을 수 있는 물건 목록</h4>{DI}
<h4>.streamlit/config.toml — 화면 설정</h4>{DT}
<div class="tip"><b>바인딩은 두 군데가 한 쌍이에요.</b> 컨테이너 안은 <code>0.0.0.0</code> 이어야 구멍이 이어지고, 밖으로 새지 않게 하는 건 compose 의 <code>127.0.0.1:</code> 이에요. 한쪽만 바꾸면 접속이 안 되거나(안 이어짐) 같은 네트워크에 노출돼요(열림).</div>
<div class="warn"><b>hwp.exe 는 상자 안에 없어요.</b> Windows 전용이라서요. 변환에는 쓰이지 않아서 영향이 없고(코드 어디서도 부르지 않아요), 개발 중 결과 검사(<code>validate</code>)·쪽 그리기(<code>render</code>)에만 썼어요. 나중에 서비스가 스스로 검사하려면 리눅스용이 필요해요.</div>
</section>

<section id="s9"><h2><span class="num">9</span>점검표 — 고쳐도 안 망가졌는지 확인하기</h2>
{kid("공장을 고칠 때마다 “옛날에 잘 되던 것이 그대로 되나?”를 사람이 일일이 확인하면 힘들어요. 그래서 <b>점검표(테스트)</b>를 만들어 두고 한 번에 돌려요. 실행: <code>python test_hwpx_roundtrip.py</code>")}
{table(["점검 묶음","무엇을 확인하나"],[
  ["공고문 왕복 OK","HWPX → HTML → HWPX 를 했더니 문단 773 · 표 42 · 칸 472 가 그대로, 글자는 99.986% 같음"],
  ["회의록 HTML OK","HTML → HWPX: 글자 손실 없음, 표 폭이 본문 폭 안, 그림 2장이 BinData 에 맞게 들어감, 다시 HTML 로 해도 그림 유지"],
  ["글머리 변환 OK","한컴 글머리(U+F09F)가 HTML 에서 진짜 • 로 나옴"],
  ["convert.py OK","HWP → HWPX → HTML 한 줄 흐름, 형식 판별, 지원하지 않는 길 거절"],
  ["입력 방어 OK","태그 없는 글 거절, CP949 HTML 변환, 압축 한도가 실제로 걸림"],
])}
<h4>“입력 방어” 점검의 실제 코드</h4>{T_DEF}
</section>

<section id="s10"><h2><span class="num">10</span>폴더 구조와 장부</h2>
<div class="tree">File-conversation/
├ app.py · convert.py · hwp2html.py · hwpx2html.py · html2hwpx.py   <i>← 공장 본체(서로 불러서 같은 폴더)</i>
├ test_hwpx_roundtrip.py · check_setup.py                            <i>← 점검표 / 설치 확인</i>
├ Dockerfile · compose.yaml · .dockerignore · .streamlit/config.toml <i>← 유리 상자</i>
├ requirements.txt · .gitignore · .env                               <i>← .env 는 비밀(이미지에 안 들어감)</i>
├ samples/            <i>원본 3개: 공고문 .hwpx · 근무계획서 .hwp · 회의록 .hwp(66MB)</i>
├ results/
│   ├ V0_수정전_변환기        <i>처음 받은 변환기(.orig)</i>
│   ├ V1_공고문_이전시도      <i>공고문을 다른 도구로 변환한 이전 결과</i>
│   ├ V2_채팅에서_만든_HTML    <i>채팅의 Claude 가 만든 회의록 HTML</i>
│   ├ V3_변환기_글머리수정전   <i>글머리 수정 전 변환기의 결과</i>
│   └ V4_현재_변환기          <i>지금 변환기의 결과(HTML + HWPX)</i>
├ docs/               <i>계획서 · 이 문서 같은 설명서</i>
├ logs/               <i>requests.jsonl (실행하면 생김, git 제외)</i>
├ tools/hwp-cli/      <i>hwp.exe (개발 중 검사용, Windows 전용)</i>
├ langfuse/           <i>Langfuse 소스·compose (지금 변환기와는 직접 관계 없음)</i>
└ .venv/              <i>컨테이너 없이 화면을 돌릴 때만 필요</i></div>
<p>결과물은 <b>V0, V1, V2 …</b> 처럼 버전 번호 폴더로 나눠요. 새 변환 결과는 다음 번호(V5)에 넣어요.</p>
<h4>장부 한 줄의 모양 (logs/requests.jsonl)</h4>
<div class="code"><div class="ch"><b>logs/requests.jsonl</b><span>실제 실행에서 나온 한 줄</span></div><pre><code><span class="l" style="white-space:pre-wrap;word-break:break-all">{{"ts": "2026-10-07T01:00:36+00:00", "kind": "hwp", "target": "hwpx", "bytes_in": 66726912, "bytes_out": 490416, "seconds": 3.04, "status": "ok", "error": null, "sha256": "838fadf992bd664d"}}</span></code></pre></div>
{table(["항목","뜻"],[
  ["ts","언제(시간대 포함: <code>+00:00</code> 은 UTC, 한국은 +09:00)"],["kind → target","무엇을 무엇으로 (hwp → hwpx)"],
  ["bytes_in / bytes_out","입력·결과 크기(바이트). 66MB 가 490KB 로 줄어든 건 BMP 사진을 JPEG 로 줄였기 때문"],
  ["seconds","걸린 시간(자리를 기다린 시간 포함)"],["status","ok · error · timeout · busy"],
  ["error","실패일 때만, 오류 한 줄(최대 200자). 본문은 안 들어가요"],["sha256","입력 파일의 지문 앞 16자리. 같은 파일인지만 알 수 있고 내용은 알 수 없어요"],
])}
<p>파일 <b>이름</b>과 <b>본문</b>은 장부에 쓰지 않아요.</p>
</section>
''')

# ---- 11. Q&A / 12. 남은 일 / 13. 용어
parts_html.append('''
<section id="s11"><h2><span class="num">11</span>왜 이렇게 됐을까 — 겪은 일들</h2>
<dl class="qa">
<dt>Q. 글머리(•)가 네모로 보였던 이유는?</dt>
<dd>한컴 HWPX 는 글머리를 브라우저가 못 그리는 <b>사설 영역 문자(U+F09F 등)</b>로 저장해요. <code>hwp2html.py</code> 에는 진짜 • 로 바꾸는 표(PUA)가 있었는데 <code>hwpx2html.py</code> 에는 없었어요. 그 표를 가져다 쓰도록 고쳤어요.</dd>
<dt>Q. 공고문에서 제목 괄호가 □ 로, 흐름도 화살표가 ⊠ 로 보였던 이유는?</dt>
<dd>같은 종류의 문제가 한 단계 더 먼 곳에 있었어요. 이 파일에는 <b>보조 평면 사설 문자</b>(<code>U+F0854</code> 『, <code>U+F0855</code> 』, <code>U+F0039</code> ⬅, <code>U+F003B</code> ⬇)가 있었어요. 한컴 렌더러로 원본을 그려 모양을 확인한 뒤 변환 표에 4개를 더했어요. 또 앞으로 모르는 사설 문자가 나와도 조용히 □ 가 되지 않도록, 변환 뒤 <b>남은 사설 문자를 세어 경고</b>로 알려 줘요(<code>convert.leftover_pua</code>).</dd>
<dt>Q. 변환을 왜 따로 프로그램(subprocess)으로 돌리나요?</dt>
<dd><code>hwp2html.py</code> 가 “프로세스당 한 건”을 전제로 짜여 있어서, 웹 화면에서 직접 부르면 동시 접속이 섞일 수 있어요. 따로 돌리면 섞이지 않고, 멈추거나 터져도 화면이 살아 있고, 시간 제한도 걸 수 있어요.</dd>
<dt>Q. Streamlit 을 왜 전역 파이썬이 아니라 <code>.venv</code> 에만 깔았나요?</dt>
<dd>전역에 깔면 <code>starlette</code> 가 0.41 → 1.7 로 올라가 이 PC 의 <code>fastapi</code>·<code>mcp</code> 가 깨질 수 있었어요(설치 전에 <code>pip install --dry-run</code> 으로 확인).</dd>
<dt>Q. 왜 “이 PC 에서만” 열었나요?</dt>
<dd>처음 띄운 서버가 같은 네트워크 전체에 열려 있었어요. 로그인이 없는 변환 서버가 열려 있으면 누구나 파일을 올려 변환기를 돌릴 수 있어서, <code>127.0.0.1</code> 로 막았어요.</dd>
<dt>Q. Agent SDK(에이전트)·Langfuse·OpenAI 는 왜 안 썼나요?</dt>
<dd>변환·판별·경로 선택은 코드로 충분했고, LLM 호출은 비용·개인정보 부담이 있어요. 점수를 모아 본 뒤 “숫자로는 못 잡는 서식 결함”이 많을 때 선택 기능으로 붙이기로 했어요.</dd>
</dl>
</section>

<section id="s12"><h2><span class="num">12</span>아직 안 된 것, 그리고 다음</h2>
<div class="warn"><b>솔직하게 확인하지 못한 것</b><br>
· 실제 브라우저에서 파일을 올리고 내려받아 보는 시험은 못 했어요(Chrome 확장이 연결되지 않아서). 화면은 Streamlit 시험 도구로 검증했어요.<br>
· 최신 결과(V4 <code>.hwpx</code>)를 <b>한컴 한글에서 열어 본 확인</b>은 아직이에요(<code>hwp-cli</code> 로 규격 검사·쪽 그리기까지만).<br>
· <code>hwp2html.py</code> 는 샘플 2건에서만 확인한 프로토타입이에요.</div>
<ul>
<li><b>결과 검증 표시</b> — 변환 뒤 글자 수·문단·표·그림이 원본과 맞는지 화면에 보여 주기(계획서 2단계 <code>compare</code> 의 최소형)</li>
<li><b>사내 공유</b> — 지금은 이 PC 전용. 공유하려면 접근 제어(프록시 기본 인증 등)가 먼저</li>
<li><b>형식 확장</b> — PDF · DOCX · Markdown (계획서 1단계)</li>
<li><b>컨테이너 안 검사·렌더</b> — <code>hwp-cli</code> 의 리눅스 빌드 확인 또는 다른 렌더러</li>
<li><b>LLM·Langfuse</b> — 점수를 모아 본 뒤 필요할 때만</li>
</ul>
</section>

<section id="s13"><h2><span class="num">13</span>낱말 풀이</h2>
''' + table(["말","쉬운 뜻"], [
    ["OLE2 (CFB)", "HWP 가 쓰는 “서랍장” 파일 방식. 칸 번호표(FAT)로 서랍 안 내용을 찾아요."],
    ["ZIP", "여러 파일을 한 장으로 묶는 지퍼백. HWPX 와 docx 가 이 방식이에요."],
    ["XML", "글자로 쓴 설명서. <code>&lt;hp:p&gt;</code> 처럼 꺾쇠 이름표로 구조를 나타내요."],
    ["매직 바이트(시그니처)", "파일 맨 앞에 새겨진 “나는 이런 파일이야” 도장. 이름을 바꿔도 안 변해요."],
    ["압축 폭탄", "작게 압축했지만 풀면 수십 GB 가 되어 컴퓨터를 멈추게 하는 파일."],
    ["사설 영역(PUA) 문자", "표준 글자가 아닌, 프로그램끼리만 약속해 쓰는 글자 번호. 브라우저는 네모로 보여요."],
    ["HWPUNIT", "한글의 길이 단위. 1pt = 100, 1px = 75."],
    ["data URI", "그림을 파일이 아니라 긴 글자(base64)로 HTML 안에 박아 넣는 방법."],
    ["SSRF", "서버를 속여 남의 주소·내 컴퓨터 파일을 몰래 읽게 하는 공격. 그래서 외부 그림 주소는 안 읽어요."],
    ["서브프로세스", "프로그램이 다른 프로그램을 따로 실행하는 것. 하나가 망가져도 다른 쪽은 살아 있어요."],
    ["세마포어", "번호표. 동시에 할 수 있는 일의 수를 세요."],
    ["컨테이너", "프로그램을 가둬 두는 유리 상자. 쓸 수 있는 파일·메모리·권한을 정해 줘요."],
    ["bind mount", "상자 안 폴더와 내 PC 폴더를 같은 곳으로 이어 주는 것(여기선 logs)."],
    ["tmpfs", "하드디스크가 아니라 메모리 위에 만든 임시 폴더."],
    ["해시(sha256)", "파일의 지문. 같은 파일이면 같은 값, 내용은 알 수 없어요."],
]) + '</section>')

HTML = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>파일 변환 공장 이야기</title><style>' + CSS + '</style></head><body>'
        '<nav class="top"><div class="in"><a class="brand" href="#top">📦 파일 변환 공장</a>'
        '<a href="#s1">이야기</a><a href="#s2">흐름</a><a href="#s3">상세 구조도</a><a href="#s4">변환 길</a><a href="#s5">파일 지도</a>'
        '<a href="#s6">코드 읽기</a><a href="#s7">안전 문</a><a href="#s8">Docker</a><a href="#s9">점검표</a><a href="#s10">폴더·장부</a><a href="#s11">겪은 일</a><a href="#s12">남은 일</a><a href="#s13">낱말</a></div></nav>'
        '<main>' + ''.join(parts_html) +
        '<footer>이 문서의 코드 조각은 프로젝트의 실제 파일에서 자동으로 뽑아 만들었어요(2026-10-07 기준). 코드를 고치면 줄 번호가 달라질 수 있어요.</footer></main></body></html>')

OUT.write_text(HTML, encoding='utf-8')
print('written', OUT, f'{len(HTML) / 1024:.0f} KB')

import base64, io, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import lib
PROJ = Path(r'D:\Company_project\File-conversation')
lib.ROOT = PROJ / 'versions' / 'V2'            # 코드 조각은 V2 에서 뽑는다
from lib import snip, code, esc
import diagrams as D
from style import CSS
from PIL import Image

SP = Path(r'C:\Users\dldbs\AppData\Local\Temp\claude\D--Company-project-File-conversation\6865fd4c-18a1-444d-936f-7b36e8ad82f0\scratchpad')
OUT = PROJ / 'docs' / 'V2_작업결과_보고서.html'
EXTRA_CSS = '''
.bar-ok{fill:#2f9e5b}.bar-warn{fill:#e0a800}.bar-bad{fill:#d64545}.bt{font-size:15px;font-weight:800;fill:#fff}
figure{margin:14px 0}figure img{max-width:100%;height:auto;border:1px solid var(--line);border-radius:10px;background:#fff}
figcaption{font-size:14px;color:var(--muted);margin-top:6px}
.pair{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px}
.ok{color:#2f9e5b;font-weight:700}.wn{color:#b7791f;font-weight:700}.bd{color:#d64545;font-weight:700}
'''


def img(path, alt, cap, maxw=860):
    im = Image.open(path).convert('RGB')
    if im.width > maxw: im = im.resize((maxw, round(im.height * maxw / im.width)))
    buf = io.BytesIO(); im.save(buf, 'PNG', optimize=True)
    return f'<figure><img alt="{esc(alt)}" src="data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"><figcaption>{cap}</figcaption></figure>'


def kid(*paras, title='쉽게 말하면'):
    return f'<div class="kid"><div class="kh">🧒 {title}</div>' + ''.join(f'<p>{p}</p>' for p in paras) + '</div>'


def dgm(svg, cap=''):
    return f'<div class="dgwrap">{svg}</div>' + (f'<p class="dgcap">{cap}</p>' if cap else '')


def table(head, rows):
    h = ''.join(f'<th>{c}</th>' for c in head)
    r = ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in row) + '</tr>' for row in rows)
    return f'<div class="tw"><table><thead><tr>{h}</tr></thead><tbody>{r}</tbody></table></div>'


# ------------------------------------------------------------------ 데이터
before = json.loads((PROJ / 'corpus/_out/before/corpus_report.json').read_text(encoding='utf-8'))
after = json.loads((PROJ / 'corpus/_out/corpus_report.json').read_text(encoding='utf-8'))
def tally(rows):
    ok = sum(r['verdict'] == '✅' for r in rows); bad = sum(r['verdict'].startswith('❌') for r in rows)
    return ok, len(rows) - ok - bad, bad
tb, ta = tally(before), tally(after)
byname = {r['file']: r for r in before}
n_hwp = sum(r.get('kind') == 'hwp' for r in after); n_hwpx = sum(r.get('kind') == 'hwpx' for r in after)
icon = lambda v: '✅' if v == '✅' else ('❌' if v.startswith('❌') else '⚠️')
rows = []
for r in after:
    b = byname[r['file']]
    rows.append([f'<code>{esc(r["file"])}</code>', r.get('kind') or '?', f'{icon(b["verdict"])} → {icon(r["verdict"])}',
                 esc(r['verdict'].lstrip('✅⚠️❌ ').strip() or '이상 없음')])
corpus_table = table(['문서(corpus/rhwp/ 아래)', '형식', '고치기 전 → 뒤', '남은 이유'], rows)
pdf_rows = [l.split(' | ') for l in (PROJ / 'corpus/_layout_out/layout_report.txt').read_text(encoding='utf-8').splitlines()[1:-2] if ' | ' in l]
old_pdf = {l.split(' | ')[0]: l.split(' | ')[1] for l in (PROJ / 'corpus/_pdfout/pdf_report.txt').read_text(encoding='utf-8').splitlines()[1:-2] if ' | ' in l}
pdf_table = table(['문서', '한컴 쪽 수', '고치기 전 우리', '지금 우리', '판정'],
                  [[f'<code>{esc(a)}</code>', c, old_pdf.get(a, '?'), f'<b>{b}</b>', ('✅ 같음' if e == 'OK' else f'⚠️ {esc(e)}')] for a, b, c, d, e in pdf_rows])
same = sum(1 for r in pdf_rows if r[4] == 'OK')
old_same = sum(1 for a, b, c, d, e in pdf_rows if old_pdf.get(a) == c)
diff_now = sum(abs(int(b) - int(c)) for a, b, c, d, e in pdf_rows)
diff_old = sum(abs(int(old_pdf.get(a, c)) - int(c)) for a, b, c, d, e in pdf_rows)

# ------------------------------------------------------------------ 코드 조각
C_SUR = code(snip('hwp2html.py', 'if 0xD800 <= ch < 0xDC00', n=4), [
    ('if 0xD800 <= ch < 0xDC00', 'UTF-16 은 U+FFFF 보다 큰 글자(보조 평면)를 <b>2칸짜리 쌍</b>(대리쌍)으로 저장해요. 예전 코드는 칸마다 따로 읽어서 <b>반쪽짜리 글자</b>가 생겼고, 파일을 쓸 때 “surrogates not allowed” 오류가 났어요.'),
    ('cp = 0x10000', '두 칸을 합쳐 진짜 글자 번호(예: <code>U+F0039</code>)를 계산해요. 이제 변환 표(PUA)에서 찾을 수 있어요.'),
    ('0xD800 <= ch < 0xE000', '짝이 없는 반쪽은 “대체 문자(�)”로 바꿔요. 그대로 두면 파일을 쓰다 터지니까요.'),
])
C_HF = code(snip('hwpx2html.py', "for kind in ('header', 'footer'):", n=15), [
    ("for kind in ('header', 'footer'):", '<b>머리글·바닥글</b>: 이전에는 통째로 사라졌어요(공문서 표가 머리글에 있으면 표가 사라짐). 이제 내용을 모아 두었다가 본문 맨 앞/끝에 넣어요. 쪽마다 반복은 못 하지만 <b>내용은 지켜져요</b>.'),
    ("if h and h not in s.hf[kind]", '홀수·짝수 쪽 머리글이 서로 다르면 둘 다, 같으면 한 번만 넣어요.'),
    ("elif tag in ('checkBtn'", '<b>서식의 체크박스·라디오·버튼</b>: 모양은 못 그리지만 <code>☐ ☑ ○ ◉</code> 기호와 설명 글은 남겨요(한 문서에서 181개가 사라지고 있었어요).'),
    ("elif tag == 'rect'", '<b>글상자</b>: 안에 든 글(“제4교시”, “(사회·문화)” 등)만 가져와요. 도형 모양과 테두리는 무시해요.'),
    ('flush(); has_table = True', '문단(<code>&lt;p&gt;</code>) 안에는 블록(<code>&lt;div&gt;</code>)을 넣을 수 없어서, 바깥도 <code>&lt;div&gt;</code> 로 바꿔요.'),
])
C_PUA = code(snip('hwp2html.py', 'PUA = {0xF09F', end='# PUA 는 글꼴별'), [
    ('0xF0854', '공고문에서 확인한 4개: 『 』 ⬅ ⬇ (한컴 렌더러로 원본 모양을 보고 정함).'),
    ('rhwp(https://github.com/edwardkim/rhwp', 'rhwp 의 “한컴 PDF 로 확인된” 표 36개를 <b>출처를 밝히고</b> 그대로 가져왔어요(MIT). 그중 2개(◇ □)는 우리 점검 문서에서도 같은 자리에 나왔어요.'),
    ('PUA[0xF53A]', '<code>U+F53A</code> 는 옛한글 “ᄒᆞᆫ”(한양 PUA 표, 퍼블릭 도메인 자료)예요. 표시하려면 옛한글을 지원하는 글꼴이 필요해요.'),
])
C_APP = code(snip('approval.py', 'def table(labels=DEFAULT):', end='def add('), [
    ('pct = min(13', '결재 칸 하나가 본문 폭의 13%(A4면 약 22mm)를 차지해요. 칸이 많으면 줄어들어요.'),
    ('spacer = 100', '남는 폭은 <b>왼쪽 빈 칸</b>으로 채워요. “오른쪽 정렬” 기능에 기대지 않고 <b>구조로</b> 오른쪽에 붙이는 방법이에요.'),
    ('blank = f', '왼쪽 빈 칸은 테두리 없음(<code>border:none</code>)이고 두 줄에 걸쳐(<code>rowspan=2</code>) 있어요.'),
    ('return (f', '이름 칸(회색 배경) 한 줄 + 서명 칸 한 줄로 된 표예요. 표 폭은 본문 폭 전체(100%)예요.'),
])
C_PDF = code(snip('convert.py', 'def _to_pdf(text, dst, d):', n=8), [
    ('from weasyprint.urls import URLFetcher', 'WeasyPrint 가 내장한 “주소 가져오는 도구”예요.'),
    ("allowed_protocols=('data',)", '<b>data: 주소만 허용</b>해요. HTML 안의 <code>file://</code> 이나 <code>http://</code> 그림·스타일을 읽으면 내 컴퓨터 파일이나 내부망이 새어 나갈 수 있어서 막아요. 막힌 자원은 빠질 뿐 변환은 계속돼요(시험으로 확인).'),
    ("return {'pages'", '만든 PDF 의 쪽 수를 돌려줘요.'),
])
C_KEPT = code(snip('check_corpus.py', 'def kept(a, b):', n=5), [
    ('def kept(a, b)', '점검 도구의 “글자 보존율”이에요. 예전에는 두 글의 <b>닮은 정도</b>를 쟀는데, 머리글이 본문 앞으로 옮겨지거나 자동 번호(“2.”)가 추가되면 손실처럼 보였어요.'),
    ('sm = difflib', '이제는 “원본 글자 중 결과에 남은 비율”을 재요. 결과에 글자가 <b>더 들어간 것</b>은 손해로 치지 않아요.'),
])

# ------------------------------------------------------------------ 페이지
P = []
P.append(f'''
<header class="hero" id="top">
  <h1>📋 V2 작업 결과 보고서</h1>
  <p>발표 피드백을 받아 한 일을 정리했어요. <b>무엇을 했고, 결과가 어떻고, 아직 안 된 게 뭔지</b>를 실제 화면과 숫자로 확인할 수 있게 썼어요. 기준일 2026-10-07.</p>
  <div class="chips">
    <span class="chip">점검 문서 <b>{len(after)}</b>건</span><span class="chip">실패 <b>{tb[2]} → {ta[2]}</b></span><span class="chip">이상 없음 <b>{tb[0]} → {ta[0]}</b></span>
    <span class="chip">새 기능 <b>2</b> (결재선 · PDF)</span><span class="chip">한컴과 같은 쪽 수 <b>{old_same} → {same}</b> / {len(pdf_rows)}</span><span class="chip">회귀 테스트 <b>10묶음 통과</b></span>
  </div>
</header>

<section id="s1"><h2><span class="num">1</span>한눈에 보기</h2>
<div class="cards">
  <div class="cardx"><div class="em">📁</div><h5>V1 보관 · V2 개발</h5><p>발표 때 상태를 V1 에 얼려 두고, 새 작업은 V2 폴더에서만 했어요.</p></div>
  <div class="cardx"><div class="em">🔬</div><h5>일반화 점검</h5><p>샘플 3건 밖의 문서 {len(after)}건으로 시험했어요. 실패 {tb[2]}건 → {ta[2]}건, 숨은 내용 손실 3종을 찾아 고쳤어요.</p></div>
  <div class="cardx"><div class="em">📚</div><h5>rhwp 조사</h5><p>기호 표 36개를 출처와 함께 가져오고, 전각·반각·글꼴 처리 방식을 배웠어요.</p></div>
  <div class="cardx"><div class="em">✍️</div><h5>결재선</h5><p>문서 맨 위 오른쪽에 “담당·검토·확인·승인” 4칸 표를 넣는 옵션을 만들었어요.</p></div>
  <div class="cardx"><div class="em">🖨️</div><h5>HTML → PDF</h5><p>HWP·HWPX·HTML 어느 것이든 PDF 로 내려받을 수 있어요(컨테이너에서).</p></div>
  <div class="cardx"><div class="em">📐</div><h5>한컴과 같은 쪽 수</h5><p>쪽 수가 같은 문서 {old_same}건 → {same}건(차이 합 {diff_old} → {diff_now}). 원인 10가지를 찾아 고쳤어요(7장).</p></div>
  <div class="cardx"><div class="em">🛡️</div><h5>안전 보강</h5><p>PDF 가 외부 파일을 읽지 못하게 막고, 장부를 못 써도 변환이 끝나게 했어요.</p></div>
</div>
{table(["피드백","처리","어디서 볼 수 있나"],[
  ["기능이 덜 됐을 때 제약조건을 설명할 것","📄 문서로 정리함(8장). 화면 안내는 아직","8장"],
  ["rhwp 를 확인해 전각·반각 처리를 학습할 것, 관련 라이브러리 확인","✅ 조사 완료","3장"],
  ["파일이 늘어나면 어떻게 될지 확인할 것","✅ 외부 문서 32건으로 점검 + 고침","4장"],
  ["html → pdf 변환 추가","✅ 완료(컨테이너에서)","6장"],
  ["결재선 추가(상단 텍스트칸 4개 표)","✅ 완료. 한컴에서 열어 본 확인은 아직","5장"],
])}
</section>

<section id="s2"><h2><span class="num">2</span>폴더 구조: V1 은 보관, V2 에서 개발</h2>
{kid("공책에 비유하면, 발표 때 쓴 공책(V1)은 서랍에 넣어 두고 <b>복사한 새 공책(V2)</b>에만 새로 적었어요. 그래서 언제든 발표 때 상태로 돌아갈 수 있어요.")}
{dgm(D.layout_v2(), "그림 1. 폴더 구조. V1 은 해시(지문)로 원본과 같음을 확인한 보관본이에요.")}
{table(["하는 일","명령(V2 폴더에서)"],[
  ["Docker 로 실행(권장, PDF 포함)","<code>docker compose up -d --build</code> → <code>http://localhost:8501</code> (이 PC 에서만 열림)"],
  ["컨테이너 없이 로컬 실행","<code>..\\..\\.venv\\Scripts\\streamlit run app.py</code> (PDF 선택지는 안 나옴)"],
  ["회귀 테스트","<code>python test_hwpx_roundtrip.py</code> (컨테이너 안에서 돌리면 PDF 검사도 실행됨)"],
  ["일반화 점검(격리 컨테이너 권장)","<code>python check_corpus.py 입력폴더 출력폴더</code>"],
])}
<div class="tip">컨테이너 이름이 <code>file-conversation-converter-1</code> 에서 <code>file-converter-converter-1</code> 로 바뀌었어요(<code>compose.yaml</code> 에 프로젝트 이름을 고정해서, 폴더 이름이 V2·V3 로 바뀌어도 그대로예요). 결과물 폴더 <code>results/V0~V4</code> 는 “변환 결과물”의 버전이고, <code>versions/V1·V2</code> 는 “코드”의 버전이에요.</div>
</section>

<section id="s3"><h2><span class="num">3</span>rhwp · pyhwpxlib 조사</h2>
{kid("rhwp 는 <b>한글 문서를 정확하게 그려 주는 프로그램</b>이에요(글자 폭까지 계산해서 한컴처럼 그려요). pyhwpxlib 는 <b>HWPX 문서를 파이썬으로 만들고 고치는 도구</b>예요. 둘은 하는 일이 달라요. 우리 변환기는 둘 다 쓰지 않고 직접 만들었어요.")}
{table(["","rhwp","pyhwpxlib","우리 코드"],[
  ["정체","Rust + WebAssembly 로 만든 HWP/HWPX 뷰어·편집기(MIT)","파이썬 라이브러리 v0.18.3 (2026-04~05, 48번 배포). 저장소 <code>ratiertm/hwpx-skill</code>","직접 만든 변환기 3개 + <code>convert.py</code>"],
  ["하는 일","HWP5·HWPX·HML 읽기, 쪽 나누기·그리기, SVG/PNG/PDF 내보내기, HWPX→HWP 저장(README 요약, 미검증)","HWPX 만들기·고치기, HWP→HWPX, 마크다운·HTML·TXT→HWPX, HWPX→텍스트·마크다운·HTML, MCP·CLI, 공문 양식","HWP→HTML, HWPX↔HTML, HWP→HWPX, (V2) →PDF, 결재선"],
  ["기반 코드","한컴 PDF 와 대조해 확인하는 방식(샘플 1,148건)","<b>hwp2hwpx·hwplib</b>(neolord0, Java, Apache 2.0)를 파이썬으로 옮김 + python-hwpx(MIT)의 모델","스스로 작성"],
  ["rhwp 와의 관계","—","README 의 “기반” 목록에는 <b>없음</b>. 대신 저장소에 <code>rhwp_bridge.py</code>, <code>vendor/rhwp_bg.wasm</code>(컴파일된 rhwp), <code>LICENSE.rhwp.txt</code> 가 있어 rhwp 를 <b>미리보기·그리기 엔진</b>으로 같이 넣어 씀","rhwp 의 검증된 기호 표(MIT)를 출처를 밝히고 가져옴"],
  ["라이선스","MIT","<b>PolyForm Noncommercial 1.0.0</b>(3개 파일만 Apache 2.0). “상업적 이용은 규모와 상관없이 별도 유료 라이선스”","우리 소유"],
])}
<div class="warn"><b>바로잡습니다.</b> 우리 변환기가 <code>pyhwpxlib</code> 를 쓴 적은 없어요. 이전 세션에서 후보로 시험만 했고 <b>상업 이용 유료</b>라서 제외한 기록이 있어요. 지금 쓰는 외부 도구는 개발 중 검사용인 <code>hwp-cli</code> 하나뿐이에요. pyhwpxlib 가 rhwp 를 “기반”으로 만들어졌다기보다 <b>rhwp 를 렌더링용으로 함께 쓰는</b> 것으로 확인돼요(PyPI·GitHub README 와 저장소 파일 목록 기준. 다른 문서에 다르게 적혀 있다면 알려 주세요).</div>
<h4>rhwp 에서 배운 것 (원문 코드·문서로 직접 확인)</h4>
{table(["주제","rhwp 방식","우리에게 주는 뜻"],[
  ["사설 영역(PUA) 문자","<code>hancom_pua.rs</code>: 한컴 PDF 로 확인된 문자만 표에 넣음(36개). “PUA 는 글꼴별 사적 영역이라 범위로 뜻을 짐작하면 안 된다”","같은 원칙으로 가기로 함. 확인된 36개를 출처와 함께 가져옴"],
  ["옛한글","<code>pua_oldhangul.rs</code>: KTUG 퍼블릭 도메인 표(5,660개)로 자모 시퀀스로 바꿈","우리는 <code>U+F53A</code> 하나만 반영. 전체 표 도입은 다음 후보"],
  ["전각·반각 폭","글자별 폭 DB 로 위치·자간·가로폭을 <b>직접 고정</b>(SVG <code>textLength</code>). 브라우저 대체 글꼴의 폭에 맡기지 않음","우리는 CSS 자간 + 설치된 글꼴에 의존 → 글꼴 환경이 다르면 줄바꿈이 달라질 수 있음(알려진 한계)"],
  ["반각 조판","옛 한양 글꼴은 영문·숫자를 한글 폭의 절반으로 조판. 한컴이 저장한 줄 나눔(<code>linesegarray</code>)을 증거로 판정","HWPX 에 줄 나눔이 들어 있음을 확인(공고문 773문단 전부). 다만 <b>파일마다 낡은 값이 들어 있을 수 있어</b> 정답지로는 못 씀(7장)"],
  ["검증 방법","샘플 1,148건 + 한컴 PDF 를 정답으로 겹쳐 비교. 점수는 참고, 사람이 판독","우리도 같은 방식으로 외부 문서 32건 점검(4장), 쪽 수 비교(6장)"],
  ["글꼴","한컴 전용 글꼴은 쓰지 않고 무료 글꼴(Noto Serif KR 등)로 대체","PDF 에는 나눔 글꼴 + 이름 대응표(<code>fonts.conf</code>)를 씀"],
])}
</section>

<section id="s4"><h2><span class="num">4</span>일반화 점검 — 샘플 3건 밖에서는 어떻게 되나</h2>
{kid(f"지금까지는 같은 문서 3개로만 시험해서 잘 되는 것처럼 보였어요. 그래서 <b>처음 보는 문서</b> {len(after)}건(HWP {n_hwp}, HWPX {n_hwpx})을 넣어 봤어요. 인터넷에서 받은 문서라, 읽기만 하는 <b>격리된 상자</b>(네트워크 없음, 읽기 전용)에서 돌렸어요.")}
{dgm(D.bars(tb, ta), f"그림 2. 점검 결과. 실패 {tb[2]}건이 {ta[2]}건으로 줄었어요(남은 1건은 HWP 3.0 이라 지원하지 않는다고 안내).")}
<h4>찾은 문제와 고친 것</h4>
{table(["찾은 문제","원인","고친 방법","결과"],[
  ["<code>pua-test.hwp</code> 외 1건: 변환 중 오류(<code>surrogates not allowed</code>)","UTF-16 대리쌍(2칸짜리 글자)을 반쪽씩 읽음","두 칸을 한 글자로 합침 (아래 코드)","✅ 변환됨"],
  ["<code>request.hwp</code>: <code>struct.error</code>","옛 형식의 표 칸 레코드가 30바이트로 더 짧음","길이를 확인하고 없으면 기본값","✅ 변환됨"],
  ["공공 공고 HWPX: <code>AttributeError</code>","테두리에 대각선 굵기 정보가 없음","없으면 기본값","✅ 변환됨"],
  ["<code>20099369_…hwp</code>: “알 수 없는 바이너리”","<b>HWP 3.0</b>(옛 형식)","알아듣는 메시지로 거절: “한글에서 HWP 5.0 또는 HWPX 로 다시 저장해 주세요”","❌ → 안내(지원 안 함)"],
  ["<code>exam_social-p1.hwpx</code>: 표 2개와 글자 사라짐","<b>머리글</b> 안의 표를 변환기가 버림","머리글·바닥글을 본문 앞/끝에 넣음","✅ 보존"],
  ["같은 문서의 글상자 글자(“제4교시” 등) 사라짐","글상자(<code>rect</code>)를 건너뜀","글상자 안 글을 가져옴","✅ 보존"],
  ["서식의 체크박스 181개 사라짐","양식 컨트롤(<code>checkBtn</code>)을 건너뜀","☐ ☑ ○ ◉ + 설명 글","✅ 보존"],
  ["기호가 □ 로 보이는 문자","사설 문자 표에 없음","rhwp 검증 표 36개 + 공고문 4개 + 옛한글 1개 추가","✅ 해당 문자 해결"],
])}
{C_SUR}
{C_HF}
{C_PUA}
{C_KEPT}
<h4>아직 남은 것 (변환은 되지만 확인이 필요)</h4>
{table(["남은 것","이유","다음에 할 일"],[
  ["미등록 사설 문자: <code>U+F007F</code>, <code>U+F0827</code>, <code>U+F076</code> 등","한컴 PDF 로 확인된 적 없는 기호","경고로 알려 주므로, 문서를 만나면 원본 모양을 확인해 표에 추가"],
  ["옛한글 3자(<code>shortcut.hwp</code>)","옛한글을 그릴 수 있는 글꼴이 필요","KTUG 전체 표 도입 + 옛한글 지원 글꼴 검토"],
  ["<code>comboBox</code>·<code>edit</code> 양식 컨트롤(<code>form-01.hwpx</code>)","글이 들어 있지 않아 건너뜀","내용이 있는 경우를 만나면 처리"],
  ["머리글·바닥글이 쪽마다 반복되지 않음","HTML 에는 쪽 개념이 없음","PDF 단계에서 쪽 머리글로 매핑 검토"],
  ["HWP 3.0","옛 형식","지원 계획 없음(안내만)"],
])}
<div class="tip"><b>전각·반각 형태 문자(U+FF00대)</b>는 {n_hwp + n_hwpx}건 중 3건에서만 나왔어요(<code>U+FF5E</code>, <code>U+FF0D</code>, 공고문의 <code>｢ ｣</code>). 설치된 글꼴이 있으면 정상으로 그려졌어요. 다만 글꼴이 다르면(컨테이너 PDF 는 나눔 글꼴) 폭이 달라져 줄바꿈이 달라질 수 있어요. 이 부분은 rhwp 의 “글자 폭 DB” 방식이 필요한 영역이에요.</div>
<h4>실제 화면으로 확인 — 공고문 (고치기 전 → 뒤)</h4>
<div class="pair">
{img(SP / 'gong/h_title.png', '고치기 전 제목', '고치기 전: 제목 괄호가 □ 로 보임')}
{img(SP / 'gong/fix_title.png', '고친 뒤 제목', '고친 뒤: 『 』 로 정상')}
{img(SP / 'gong/h_flow.png', '고치기 전 흐름도', '고치기 전: 흐름도 아래 화살표가 ⊠ 로 보임')}
{img(SP / 'gong/fix_flow.png', '고친 뒤 흐름도', '고친 뒤: ⬅ ⬇ 화살표 정상')}
</div>
<details class="fold"><summary>점검한 문서 {len(after)}건 전체 결과 보기</summary>{corpus_table}</details>
</section>

<section id="s5"><h2><span class="num">5</span>결재선 — 문서 맨 위 오른쪽 4칸 표</h2>
{kid("공문서 맨 위에 “담당 / 검토 / 확인 / 승인” 도장 찍는 칸이 있죠? 변환할 때 <b>체크만 하면</b> 그 표를 문서 맨 위 오른쪽에 끼워 줘요. 칸 이름은 바꿀 수 있고 최대 8칸까지예요.")}
{img(SP / 'appr/appr3.png', '결재선이 들어간 회의록 HWPX 를 hwp-cli 로 그린 모습', '회의록을 HWPX 로 변환(결재선 4칸)한 뒤 hwp-cli 로 그린 모습. 규격 검사도 통과했어요.', 520)}
{C_APP}
<h4>쓰는 방법</h4>
{table(["어디서","방법"],[
  ["화면","변환 형식을 고른 뒤 “문서 맨 위 오른쪽에 결재선 넣기”를 체크하고 칸 이름을 쉼표로 적기"],
  ["명령줄","<code>python convert.py 입력 출력 --approval 담당,검토,확인,승인</code>"],
  ["HTML·HWPX·PDF","모두 같은 표가 들어가요(변환 전에 HTML 에 표를 끼우는 방식이라서)"],
])}
<div class="warn"><b>알아 둘 점.</b> ① 처음에는 “떠 있는 표 + 오른쪽 정렬”로 만들었는데 <code>hwp-cli</code> 렌더러에서는 왼쪽에 붙어서, 정렬에 기대지 않는 <b>빈 칸 구조</b>로 바꿨어요. ② 한컴 한글에서 직접 열어 본 확인은 아직 못 했어요. ③ 회의록처럼 큰 표(칸 하나가 약 169mm)가 있는 문서는 결재선 때문에 본문 표가 다음 쪽으로 넘어갈 수 있어요(문서 구조 때문이고, 결재선 오류가 아니에요).</div>
</section>

<section id="s6"><h2><span class="num">6</span>HTML → PDF</h2>
{kid("HWP·HWPX·HTML 중 무엇을 올려도 <b>PDF</b> 로 받을 수 있게 했어요. 먼저 HTML 로 바꾼 뒤 PDF 로 찍어요. PDF 를 찍는 도구는 두 가지를 비교해서 골랐어요.")}
{dgm(D.routes_v2(), "그림 3. V2 의 변환 길. PDF 는 HTML 을 거치고, 결재선은 어느 길이든 앞에서 끼워져요.")}
{table(["후보","결과","결정"],[
  ["WeasyPrint (파이썬, 가벼움)","컨테이너 보안 설정(권한 제거·읽기 전용)과 그대로 맞음. 외부 주소를 읽지 못하게 직접 제한 가능","✅ <b>선택</b>"],
  ["Chromium (Edge 로 시험)","같은 HTML 의 쪽 수가 WeasyPrint 와 거의 같음(12/12, 15/16, 4/4, 4/4, 2/2, 2/2). 컨테이너에서는 브라우저 샌드박스가 현재 보안 설정과 충돌할 수 있고 훨씬 큼","❌ 이점 없음"],
])}
<p>이미지에는 <b>나눔 글꼴(무료)</b>과 이름 대응표가 들어가요. 한컴 글꼴 이름(함초롬바탕, 휴먼명조, 맑은 고딕 등)이 나눔명조·나눔고딕으로 대신 그려져요. 이미지 크기는 <b>923MB</b>예요.</p>
{C_PDF}
<div class="pair">
{img(SP / 'pdftest/m_p1.png', '결재선이 들어간 회의록 PDF 1쪽', '회의록 → PDF(결재선 포함): 5.2초, 2쪽, 글머리·표 정상', 520)}
{img(SP / 'pdftest/g_flow.png', '공고문 PDF 12쪽 흐름도', '공고문 → PDF 12쪽: 『 』 · ⬅ ⬇ 기호가 PDF 에서도 정상', 560)}
</div>
<h4>한컴이 만든 PDF 와 쪽 수 비교 (정답지가 있는 {len(pdf_rows)}건)</h4>
{pdf_table}
<div class="tip"><b>쪽 수가 같은 문서는 {old_same}/{len(pdf_rows)}건 → {same}/{len(pdf_rows)}건</b>, 쪽 수 차이의 합은 <b>{diff_old} → {diff_now}</b> 이에요. 처음에는 “PDF 도구 탓”이라 생각했는데, 엔진을 바꿔도 같아서 <b>우리 HTML 레이아웃</b>이 원인이었고, 그 원인들을 찾아 고친 과정이 다음 장이에요.</div>
</section>

<section id="s7"><h2><span class="num">7</span>한컴과 같은 쪽 수로 — 원인을 찾아 고친 과정</h2>
{kid("한컴이 만든 PDF 를 <b>정답지</b>로 놓고, 우리 PDF 가 몇 쪽인지 비교했어요. 어긋나는 문서를 하나 골라 <b>한컴 PDF 와 우리 PDF 의 글줄 위치를 나란히 찍어 보면서</b> 차이가 처음 생기는 곳을 찾았고, 찾을 때마다 고쳐서 쪽 수를 다시 쟀어요. 원인은 한 가지가 아니라 작은 차이 여러 개였어요.")}
{table(["원인","어떻게 찾았나","고친 방법","효과"],[
  ["<b>문단 사이 ‘줄바꿈 글자’가 빈 줄로 그려짐</b> (HWPX)","실제 문서의 첫 문단 3개만 따로 PDF 로 찍고 CSS 를 하나씩 빼 보니, <code>white-space:pre-wrap</code> 을 빼면 문단 간격이 한컴과 같아졌어요(22.4pt)","바깥 상자만 <code>white-space:normal</code>","연구설계서 15쪽 → 9쪽 (가장 큰 원인. 크롬에서도 같았어요)"],
  ["<b>줄 간격을 재는 방식이 달랐어요</b>","한컴 표에서 글자 12pt 한 줄 칸의 높이가 <b>14.82pt = 12pt + 여백 2.82pt</b>. 우리는 22pt. 한컴은 줄 간격(160%)을 <b>줄 아래에만</b> 붙이고, 칸의 마지막 줄 뒤에는 안 붙여요. CSS 는 줄 위아래로 반씩 붙여요","칸 안 첫·끝 문단에서 (줄간격−1)÷2 × 글자 크기만큼 되돌림(음수 여백)","form-002 13→10쪽, 연구설계서 9→8쪽, 실험노트 3→2쪽 (HWPX 전부 한컴과 일치)"],
  ["<b>아주 큰 칸이 통째로 다음 쪽으로 밀림</b>","한 칸이 635pt 인 서술란. 칸 높이를 지정해 두면 PDF 도구가 쪽 끝에서 나눈 앞부분도 635pt 로 쳐서 칸 전체를 밀어요","200pt 넘고 글이 가득한 칸은 높이 지정을 뺌","form-002 15→14쪽"],
  ["<b>눈에 안 보이는 빈 문단이 빈 쪽을 만듦</b>","쪽 나누기 바로 앞 빈 문단이 쪽 끝에 아슬아슬하게 걸려 넘침","쪽 나누기 앞·문서 끝의 빈 문단은 뺌","빈 쪽 3개 제거"],
  ["<b>HWP 는 글꼴을 아예 안 썼어요</b>","그림으로 보니 한컴은 고딕, 우리는 명조. 코드에서 글꼴 이름을 읽어 놓고 CSS 로 안 내보내고 있었어요","글꼴 이름 반영(고딕·명조 계열 대체 지정)","HWP 전체 글자 모양"],
  ["<b>HWP 는 자간(글자 사이)을 안 썼어요</b>","문서의 글자 모양 대부분이 자간 −5~−9%. 우리는 5~8% 넓게 그려 줄이 더 꺾였어요","자간을 전각/반각 조각으로 나눠 적용","form-002.hwp 14→10쪽"],
  ["<b>HWP 표 제목(캡션)을 칸으로 잘못 읽음</b>","<code>request.hwp</code> 의 ‘성명’ 줄이 사라져서 레코드 순서를 덤프해 보니, 표 앞에 제목 레코드가 붙어 있었어요","제목은 표 위/아래 문단으로 분리","첫 줄(성명·실명기입) 복구"],
  ["<b>HWP 의 체크박스 180개, 글상자 글이 통째로 사라짐</b>","한컴 PDF 에는 ☐ ☑ 와 제목 글이 보이는데 우리는 없음","양식 컨트롤의 <code>Caption</code>·<code>Value</code> 글을 읽어 ☐/☑, 글상자 문단·그림 크기 반영","내용 손실 해소"],
  ["HWP <b>쪽 나누기</b> 표시를 안 읽음","<code>shortcut.hwp</code> 6쪽(정답 7)","문단 머리의 쪽 나누기 비트 반영","7쪽으로 일치"],
  ["가운데 줄이 그어진 글자","취소선 비트가 ‘없음’ 자리표시 값(15)일 때도 선을 그림","값 15 는 취소선 아님으로 처리(HWPX 에서도 같은 값 확인)","한컴과 같은 모양"],
])}
<div class="pair">
{img(SP / 'layout_imgs/f2_ref.png', '한컴이 만든 PDF', '한컴 PDF (정답): form-002.hwp 위쪽', 560)}
{img(SP / 'layout_imgs/f2_ours.png', '우리 PDF', '우리 PDF (고친 뒤): 체크박스·글꼴·줄 위치가 거의 같아요', 560)}
</div>
<div class="pair">
{img(SP / 'layout_imgs/rq_ref.png', '한컴이 만든 PDF', '한컴 PDF (정답): request.hwp', 420)}
{img(SP / 'layout_imgs/rq_ours.png', '우리 PDF', '우리 PDF (고친 뒤): 표·글상자 글은 나오지만 떠 있는 틀 위치는 못 맞춰 2쪽이 돼요', 420)}
</div>
<h4>사용자가 새로 준 예시 4건 (<code>samples/</code>) — 같은 방식으로 점검</h4>
{table(["문서","hwp-cli 쪽 수","우리 쪽 수","확인한 것 · 남은 점"],[
  ["<code>공공기관 서식한글 개발 및 보급 계획.hwp</code>","2","2","머리말 표·제목 상자·그림 흐름도 모두 나옴. 머리말 표의 글이 한컴보다 한 줄 더 꺾임(글꼴 폭 차이)"],
  ["<code>공문서양식.hwp</code>","1","1","<b>머리말 안의 육군 로고</b>가 나옴(고치기 전엔 통째 사라짐). 휴먼명조 기호 <code>U+F06D</code> 는 한컴에서 ❍ 로 보임을 확인해 반영"],
  ["<code>공문서-양식-hwp.hwp</code>","3","3","표 6개·꼬리말 OK. 같은 ❍ 기호 반영. 꼬리말이 구역마다 다르면 첫 번째만 씀"],
  ["<code>표준-공문-양식-한글-원본파일-1.hwp</code>","1","1","이상 없음"],
])}
<div class="pair">
{img(SP / 'layout_imgs/n2_ref.png', '한컴급 렌더(hwp-cli)', 'hwp-cli 렌더: 공문서양식.hwp 1쪽', 460)}
{img(SP / 'layout_imgs/n2_ours.png', '우리 PDF', '우리 PDF: 로고·제목 선·표 모양이 같고, 줄 앞 기호도 ❍ 로 나와요', 460)}
</div>
{table(["새 문서에서 나온 구멍","고친 방법"],[
  ["HWP <b>머리말·꼬리말</b>을 통째로 버림(로고 소실)","내용이 있는 첫 머리말·꼬리말을 PDF 의 쪽 여백 상자로 보내 <b>쪽마다 반복</b>(한컴은 본문이 아니라 위쪽 여백 안에 그림. 본문 흐름에 넣었더니 쪽이 늘어서 바꿈)"],
  ["<code>U+F071</code>(HY헤드라인M 제목 기호)가 □ 로 나옴","hwp-cli 렌더가 ❑ 로 그린 것을 확인해 표에 추가. 같은 문서의 다른 제목은 진짜 글자 ❑ 였어요"],
  ["공문서 제목의 반각 꺾쇠 <code>｢ ｣</code> 가 PDF 에서 ⊠ 로 나옴","PDF 용 나눔 글꼴에 글자가 없어서, PDF 만 모양이 같은 <code>「 」</code> 로 바꿔 찍음(HTML 은 원문 그대로)"],
])}
<div class="tip"><b>확인 완료.</b> <code>U+F06D</code>(휴먼명조)는 hwp-cli 가 그리지 않아 모양을 몰랐는데, 사용자가 한컴 한글에서 <b>❍</b> 로 보임을 직접 확인해서 변환 표에 넣었어요. 같은 문서의 <code>U+F071</code> 은 ❑ 였어요.</div>
<h4>HWP → HWPX 는 hwp-cli 로 바꿨어요 (사용자 결정)</h4>
{table(["측정(공개 문서 15건, 한컴 PDF 와 비교)","쪽 수 일치","모양 유사도","글 보존(25건)"],[
  ["원본 HWP 를 직접 렌더(상한)","12/15","0.51","-"],
  ["<b>hwp-cli 직접 HWPX 변환 (지금)</b>","10/15","0.34","<b>100%</b>"],
  ["자체 변환기(HTML 을 거침, 이전)","9/15","0.27","96.2% (BookReview 는 15%)"],
])}
{table(["상황","동작"],[
  ["보통 문서","hwp-cli 로 직접 변환(1~2초). 원본 구조·글이 그대로 넘어가요"],
  ["결재선 옵션을 켠 경우","HTML 에 표를 끼우는 방식이라 자체 변환기를 쓰고, 그렇다는 경고를 보여 줘요"],
  ["hwp-cli 가 없거나 실패·60초 초과","자동으로 자체 변환기로 바꿔요(그림 큰 66MB 문서: hwp-cli 88초·62MB, 자체 5초·0.5MB)"],
  ["양식 입력칸·체크박스가 든 문서","hwp-cli 는 HWPX 로 못 옮기고 손실 보고서를 줘요 → “컨트롤 N개가 옮겨지지 않았습니다” 경고로 화면에 표시"],
  ["깨진 파일","긴 오류 목록 대신 “파일이 손상되었거나 읽을 수 없는 구조입니다” 한 줄"],
])}
<div class="tip">HTML·PDF 는 그대로 자체 변환기예요. hwp-cli 도 HTML 변환을 지원하지만 읽기용 HTML(표 폭 100%, 칸 크기·쪽 설정 없음)이라 모양 유사도가 0.20으로, 자체 변환기(0.40)의 절반이었어요. hwp-cli 는 Docker 이미지에 공식 릴리스(v1.3.1)를 받아 <b>공개된 체크섬이 맞을 때만</b> 설치하고(다르면 빌드 실패), MIT/Apache 라이선스 문서를 함께 둬요.</div>
<h4>사용자 업무서신(<code>business-government-letter-01.hwp</code>)도 같은 방식으로 다시 확인</h4>
{img(SP / 'letterout/letter_p1.png', '고친 뒤 업무서신 PDF 1쪽', '업무서신 → PDF 1쪽(고친 뒤). 파란 선·점선 박스·표 칸이 그대로고, “차관”과 “대표이사”가 같은 가로칸에 있어요. 쪽 수(2쪽)는 hwp-cli 가 만든 PDF 와 같아요.', 520)}
<div class="tip"><b>차관·대표이사가 엇갈렸던 이유:</b> HWP 표 칸의 세로 정렬(위·가운데·아래)을 속성값의 엉뚱한 자리(21~22번째 비트)에서 읽고 있었어요. 올바른 자리(5~6번째 비트)로 고쳤고, hwp-cli 가 읽은 값과 18칸 모두 일치함을 확인했어요. 이 문서에서는 모든 칸이 ‘가운데’였는데 우리는 전부 ‘위’로 그렸던 거예요.</div>
<div class="warn"><b>이번에 배운 점 · 아직 남은 것</b><br>
· 남은 어긋남 3건(<code>request.hwp</code>, <code>calendar_year.hwp</code>, <code>BookReview.hwp</code>): 쪽·문단에 <b>떠 있는 글상자·도형</b>의 위치(절대 좌표)를 못 맞춰요. 지금은 글이 사라지지 않게 문서 흐름 안에 놓아서 쪽이 늘어요. 도형 테두리·쪽 테두리·장평(글자 가로 비율)·HWP 머리글/바닥글도 아직 안 읽어요.<br>
· HWPX 에 든 줄 나눔 정보(<code>linesegarray</code>)는 <b>정답지로 쓸 수 없는 파일</b>이 있었어요(form-002 는 칸 글 높이를 306pt 로 적었는데 한컴이 실제로 그린 건 훨씬 길었어요). 그래서 3장 표의 “정답지로 쓸 수 있음”은 <b>파일마다 다르다</b>로 고쳐 읽어 주세요.<br>
· 비교 기준은 <b>쪽 수</b>와 눈으로 본 몇 장이에요. 글자 하나하나의 위치까지 맞는다는 뜻은 아니에요. 그리고 rhwp 저장소의 <code>basic/</code> 정답 PDF 는 문서마다 그리는 방식이 일정하지 않았어요(<code>BookReview.hwp</code> 정답에는 떠 있는 글상자 글이 없어요).</div>
</section>

<section id="s8"><h2><span class="num">8</span>지원 범위와 제약조건 (피드백 1번)</h2>
{kid("“다 되는 것처럼” 보이면 안 되니까, <b>되는 것과 안 되는 것</b>을 솔직하게 적어 둘게요.")}
{table(["구분","내용"],[
  ["✅ 되는 변환","HWP→HTML · HWPX↔HTML · HWP→HWPX(hwp-cli 직접) · (컨테이너) HTML·HWP·HWPX→PDF · 결재선 옵션"],
  ["❌ 안 되는 변환","HTML→HWP · HWPX→HWP(HWP 로 저장하는 건 범위 밖. HWPX 를 받아 한글에서 다시 저장) · HWP 3.0 · 암호·배포용·DRM 문서 · PDF/DOCX 입력"],
  ["⚠️ HWP 읽기","직접 해석하는 부분 구현이라 새 문서마다 구멍이 날 수 있음. 지금은 글꼴·자간·표(테두리·폭·세로 정렬·제목)·쪽 설정·쪽 나누기·체크박스·글상자 글·그림 크기까지 읽음. 첫 구역만, 머리글·바닥글·도형 테두리·장평은 아직"],
  ["⚠️ 레이아웃",f"정답 PDF {len(pdf_rows)}건 중 {same}건은 쪽 수가 같음(7장). 쪽·문단에 떠 있는 글상자·도형은 위치를 못 맞춰 제자리 흐름에 놓임. 머리글·바닥글은 본문 앞/끝에 한 번만"],
  ["⚠️ 글꼴·폭","한컴 글꼴이 없는 환경에서는 대체 글꼴로 그려져 폭·줄바꿈이 달라질 수 있음. 전각·반각 폭은 글꼴에 의존"],
  ["⚠️ 기호","확인된 한컴 기호 약 40종만 변환. 나머지는 □ 로 보일 수 있고, 변환 뒤 경고로 알려 줌"],
  ["⚠️ 확인 범위","샘플 3건 + 외부 문서 32건. <b>한컴 한글에서 직접 열어 본 확인은 없음</b>(hwp-cli 로 규격 검사·그리기까지만)"],
])}
</section>

<section id="s9"><h2><span class="num">9</span>확인하지 못한 것, 그리고 다음</h2>
<div class="warn"><b>솔직하게 확인하지 못한 것</b><br>
· 한컴 한글에서 V2 결과(결재선 포함 HWPX)를 직접 열어 보지 못했어요.<br>
· 실제 브라우저에서 파일을 올리고 내려받는 클릭 시험은 못 했어요(화면 시험 도구로 검증).<br>
· rhwp 를 직접 빌드해서 써 보지는 않았어요. 소스 일부와 문서만 읽었어요.<br>
· 점검 문서 32건은 모두 rhwp 저장소의 샘플이라 <b>사내 문서의 실제 분포</b>와 다를 수 있어요.</div>
{table(["다음 후보","이유"],[
  ["한컴 한글에서 V2 결과 열어 보기","결재선·기호·표 모양의 최종 확인"],
  ["한양 PUA 전체 표(KTUG) 도입 + 글꼴별 PUA 처리","옛한글 문서 대비. PUA 가 글꼴별이라는 rhwp 원칙 반영"],
  ["떠 있는 글상자·도형의 위치(절대 좌표)와 테두리, HWP 머리글·바닥글, 장평","남은 쪽 수 차이 3건의 원인(7장)"],
  ["사용자가 주는 예시 파일(<code>samples/</code>)로 같은 점검","새 문서에서 어떤 구멍이 나는지 확인 — 이번처럼 한컴 PDF 와 줄 위치를 나란히 비교"],
  ["rhwp 를 검증용 렌더러로 써 보기","한컴 PDF 없이도 시각 비교 가능, HWPX→HWP 저장 가능성"],
  ["사내 실제 문서로 점검 확대","이번 점검은 외부 샘플 기준"],
  ["화면에 ‘지원 범위·제약’ 안내 추가","피드백 1번을 화면에도 반영"],
])}
</section>
''')

NAV = ''.join(f'<a href="#s{i}">{t}</a>' for i, t in ((1, '한눈에'), (2, '폴더'), (3, 'rhwp·pyhwpxlib'), (4, '일반화 점검'), (5, '결재선'), (6, 'PDF'), (7, '쪽 수 맞추기'), (8, '제약조건'), (9, '남은 일')))
HTML = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>V2 작업 결과 보고서</title><style>' + CSS + EXTRA_CSS + '</style></head><body>'
        f'<nav class="top"><div class="in"><a class="brand" href="#top">📋 V2 보고서</a>{NAV}</div></nav><main>' + ''.join(P) +
        '<footer>코드 조각은 프로젝트의 versions/V2 실제 파일에서 자동으로 뽑았고, 점검 결과표와 화면 캡처는 실제 실행 결과예요. 이전 설명서(<code>쉬운_설명_파일변환_전체구조.html</code>)는 V1 기준이에요.</footer></main></body></html>')
OUT.write_text(HTML, encoding='utf-8')
print('written', OUT, f'{len(HTML) / 1024:.0f} KB')

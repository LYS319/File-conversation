from lib import svg, node, group, edge, note, esc


def flow():
    s = ''
    s += node(330, 10, 260, 56, ['사용자 (웹 브라우저)', 'http://localhost:8501'], 'n5')
    s += node(290, 110, 340, 70, ['app.py · 안내 데스크', 'Streamlit 화면 · 자리 3칸 · 장부 기록'], 'n1')
    s += node(290, 240, 340, 70, ['convert.py · 접수 창구', '형식 판별 → 변환 길 고르기'], 'n2')
    s += node(20, 370, 200, 70, ['hwp2html.py', 'HWP → HTML'], 'n3')
    s += node(250, 370, 200, 70, ['hwpx2html.py', 'HWPX → HTML'], 'n3')
    s += node(480, 370, 200, 70, ['html2hwpx.py', 'HTML → HWPX'], 'n3')
    s += node(710, 370, 190, 70, ['HWP → HWPX', '왼쪽 1번 다음 3번을 이어서'], 'n3', dashed=True)
    s += node(290, 520, 340, 60, ['결과 파일 (.html / .hwpx)'], 'n4')
    s += node(700, 115, 200, 60, ['logs/requests.jsonl', '요청마다 한 줄 (장부)'], 'n5')
    s += edge([(440, 66), (440, 110)], '① 파일 올리기', 430, 92, anchor='end')
    s += edge([(480, 110), (480, 66)], '⑫ 내려받기', 490, 92, anchor='start')
    s += edge([(460, 180), (460, 240)], '⑦ 새 프로세스로 호출', 472, 214, anchor='start')
    s += edge([(400, 310), (120, 370)]) + edge([(440, 310), (350, 370)]) + edge([(480, 310), (580, 370)]) + edge([(520, 310), (805, 370)])
    s += note(640, 262, ['ROUTES 표에서 (입력, 출력)', '쌍으로 변환기를 고름'])
    s += edge([(120, 440), (300, 520)]) + edge([(350, 440), (380, 520)]) + edge([(580, 440), (540, 520)]) + edge([(805, 440), (620, 520)])
    s += edge([(290, 550), (10, 550), (10, 145), (290, 145)], None)
    s += note(18, 330, ['⑩⑪ 결과를 바이트로', '돌려받음'])
    s += edge([(630, 145), (700, 145)], '기록', 665, 137)
    return svg(920, 600, s, '전체 흐름: 브라우저에서 app.py, convert.py, 변환기 3개를 거쳐 결과 파일이 돌아오는 그림')


def routes():
    s = ''
    s += node(20, 70, 170, 100, ['HWP', '.hwp', '옛 한글 파일'], 'n3')
    s += node(365, 70, 170, 100, ['HTML', '.html', '브라우저가 보는 글'], 'n1')
    s += node(710, 70, 170, 100, ['HWPX', '.hwpx', '새 한글 파일'], 'n2')
    s += edge([(190, 105), (365, 105)], 'hwp2html.py', 277, 96)
    s += edge([(535, 105), (710, 105)], 'html2hwpx.py', 622, 96)
    s += edge([(710, 140), (535, 140)], 'hwpx2html.py', 622, 162)
    s += edge([(105, 70), (105, 28), (795, 28), (795, 70)], 'HWP → HWPX : 위 두 단계를 convert.py가 이어서 한 번에', 450, 20)
    s += note(20, 230, ['지원하지 않는 길(요청하면 "지원하지 않는 변환"으로 거절):',
                        'HTML → HWP, HWPX → HWP (HWP로 저장하는 건 범위 밖. HWPX를 받아 한글에서 다시 저장하도록 안내),',
                        '같은 형식끼리(hwp → hwp, hwpx → hwpx 등)'], cls='ts')
    return svg(900, 290, s, '변환 길 지도: HWP, HTML, HWPX 사이의 화살표')


def filemap():
    s = ''
    s += node(20, 10, 260, 56, ['Dockerfile · compose.yaml', '.dockerignore (포장 설명서)'], 'n4')
    s += node(320, 10, 280, 56, ['app.py', '화면 + 자리·시간·장부'], 'n1')
    s += node(680, 10, 220, 56, ['logs/requests.jsonl', '장부 (실행하면 생김)'], 'n5')
    s += node(320, 120, 280, 56, ['convert.py', '판별 + 변환 길 표(ROUTES)'], 'n2')
    s += node(40, 250, 220, 56, ['hwp2html.py', 'HWP → HTML'], 'n3')
    s += node(350, 250, 220, 56, ['hwpx2html.py', 'HWPX → HTML'], 'n3')
    s += node(660, 250, 220, 56, ['html2hwpx.py', 'HTML → HWPX'], 'n3')
    s += node(320, 390, 280, 56, ['test_hwpx_roundtrip.py', '점검표 (회귀 테스트)'], 'n4')
    s += edge([(280, 38), (320, 38)], '포장', 300, 28, dashed=True, anchor='middle')
    s += edge([(600, 38), (680, 38)], '기록', 640, 30)
    s += edge([(460, 66), (460, 120)], '새 프로세스로 호출', 472, 98, anchor='start')
    s += edge([(380, 176), (150, 250)]) + edge([(460, 176), (460, 250)]) + edge([(540, 176), (770, 250)])
    s += edge([(350, 278), (260, 278)], 'PUA 글머리 표', 305, 268, dashed=True)
    s += edge([(380, 390), (150, 306)], None, dashed=True) + edge([(460, 390), (460, 306)], None, dashed=True) + edge([(540, 390), (770, 306)], None, dashed=True)
    s += note(470, 350, ['함수를 직접 불러서 확인'], cls='ts')
    return svg(920, 470, s, '파일 지도: 어떤 파일이 어떤 파일을 부르는지')


def gates():
    s = ''
    s += node(20, 40, 270, 96, ['① 올릴 때', '파일 크기 100MB 이하', '(Streamlit 설정)'], 'n1')
    s += node(325, 40, 270, 96, ['② 종류 확인', 'HWP·HWPX·HTML만 통과', 'exe·태그 없는 글은 거절'], 'n2')
    s += node(630, 40, 270, 96, ['③ 자리 3칸', '동시에 3개까지', '60초 기다려도 없으면 "바쁨"'], 'n3')
    s += node(630, 210, 270, 96, ['④ 시간 120초', '넘으면 변환 프로세스를', '강제로 끝냄'], 'n4')
    s += node(325, 210, 270, 96, ['⑤ 압축 풀기 한도', 'HWP 스트림 하나당 512MB', 'HWPX 전체 1GB'], 'n2')
    s += node(20, 210, 270, 96, ['⑥ 그림 한도', '그림 100MB 이하', '1억 화소 이하'], 'n1')
    s += node(20, 350, 270, 60, ['변환 성공 → 장부 한 줄', 'logs/requests.jsonl'], 'n5')
    s += edge([(290, 88), (325, 88)]) + edge([(595, 88), (630, 88)]) + edge([(765, 136), (765, 210)])
    s += edge([(630, 258), (595, 258)]) + edge([(325, 258), (290, 258)]) + edge([(155, 306), (155, 350)])
    s += note(325, 350, ['어느 문에서든 걸리면 → 이유를 화면에 보여 주고', '그 사실도 장부에 남김(오류·시간 초과·바쁨).', '파일 이름과 본문은 장부에 쓰지 않음.'])
    return svg(920, 430, s, '안전 문 순서: 업로드 크기, 종류 확인, 자리, 시간, 압축 한도, 그림 한도')


def docker():
    s = ''
    s += group(10, 10, 330, 360, '내 PC (Windows)', 'g1')
    s += node(30, 50, 290, 56, ['웹 브라우저', 'http://localhost:8501'], 'n5')
    s += node(30, 140, 290, 56, ['127.0.0.1:8501', '(이 PC 안에서만 열린 문)'], 'n2')
    s += node(30, 290, 290, 56, ['./logs 폴더', 'requests.jsonl 이 여기에 남음'], 'n5')
    s += edge([(175, 106), (175, 140)])
    s += group(400, 10, 510, 440, 'Docker 컨테이너 (유리 상자)', 'g2')
    s += node(420, 50, 230, 70, ['Streamlit', 'app.py (안내 데스크)'], 'n1')
    s += node(680, 50, 210, 70, ['convert.py', '(새 프로세스로 실행)'], 'n2')
    s += node(420, 160, 230, 60, ['/tmp (메모리 1GB 임시칸)', '업로드 임시 파일'], 'n4')
    s += node(680, 160, 210, 60, ['/app (읽기 전용)', '코드 5개 + 설정'], 'n3')
    s += edge([(650, 85), (680, 85)], None)
    s += note(420, 262, ['• 일반 사용자(uid 10001)로 실행 — 관리자 아님',
                         '• 리눅스 특수 권한 전부 제거 (cap_drop ALL)',
                         '• 읽기 전용 파일시스템 (쓰기는 /tmp 와 logs 만)',
                         '• 메모리 3GB · CPU 2개 · 프로세스 256개 상한',
                         '• .env(API 키)·samples·langfuse 는 이미지에 안 들어감',
                         '• 죽거나 Docker가 다시 켜지면 자동으로 다시 뜸 (restart)'], cls='ts')
    s += edge([(320, 168), (420, 90)], '포트 매핑', 372, 118, anchor='middle')
    s += edge([(400, 318), (320, 318)], 'bind mount', 360, 308, dashed=True)
    s += node(10, 395, 330, 56, ['같은 네트워크의 다른 PC', '접속 불가 (127.0.0.1 만 열림)'], 'n5', dashed=True)
    s += edge([(175, 395), (175, 374)], bad=True)
    return svg(920, 470, s, 'Docker 구조: 내 PC의 브라우저가 127.0.0.1:8501 을 통해 컨테이너 안의 Streamlit과 만나는 그림')


def hwp_inside():
    s = ''
    s += group(10, 10, 900, 405, '파일 하나: 안전관리_회의록_20241029.hwp (63.6MB)', 'g1')
    s += group(30, 48, 860, 355, 'OLE2 서랍장(CFB) — 칸(섹터) 번호표(FAT)를 따라가면 서랍 안 내용을 읽을 수 있다', 'g2')
    s += node(50, 90, 190, 120, ['/FileHeader', '이름표', '"HWP Document File"', '압축? 암호? 깃발'], 'n5')
    s += node(260, 90, 190, 120, ['/DocInfo', '설계도 (압축됨)', '글꼴·글자 모양', '문단 모양·테두리'], 'n2')
    s += node(470, 90, 190, 120, ['/BodyText/Section0', '본문 (압축됨)', '문단 레코드 나무', '(글자·표·그림 자리)'], 'n1')
    s += node(680, 90, 190, 120, ['/BinData/BIN0001.bmp…', '사진 (압축됨)', '이 문서는 BMP 2장', '풀면 장당 약 70MB'], 'n3')
    s += node(50, 260, 190, 56, ['load()', '도장·깃발 확인'], 'n4')
    s += node(260, 260, 190, 56, ['load() + dec()', '모양 표 읽기'], 'n4')
    s += node(470, 260, 190, 56, ['tree() + render_paras()', '글·표·그림을 HTML로'], 'n4')
    s += node(680, 260, 190, 56, ['bindata_uri()', 'JPEG로 줄여 글에 넣음'], 'n4')
    for x in (145, 355, 565, 775): s += edge([(x, 210), (x, 260)])
    s += note(50, 345, ['dec() = 압축 풀기. 풀린 크기가 스트림당 512MB를 넘으면 거절(압축 폭탄 방어).',
                        '회의록의 BMP 사진은 장당 약 70MB라서, 한도를 100MB로 잡으면 정상 문서가 막힙니다.'])
    return svg(920, 425, s, 'HWP 파일 내부: OLE2 서랍장 안의 FileHeader, DocInfo, BodyText, BinData')


def hwpx_inside():
    s = ''
    s += group(10, 10, 900, 400, 'HWPX = 지퍼백(ZIP) 한 장', 'g1')
    s += node(30, 55, 200, 76, ['mimetype', 'application/hwp+zip', '맨 앞 · 압축 안 함'], 'n5')
    s += node(30, 150, 200, 60, ['version · settings', 'META-INF (꼬리표 파일)'], 'n5')
    s += node(270, 55, 300, 100, ['Contents/header.xml', '"사전": 글자 모양(charPr)', '문단 모양(paraPr) · 테두리', '번호 매기기'], 'n2')
    s += node(270, 205, 300, 100, ['Contents/section0.xml', '"글": 문단(hp:p) · 표(hp:tbl)', '그림(hp:pic) 이 사전의 번호를', '가리키며 적혀 있음'], 'n1')
    s += node(610, 55, 280, 60, ['Contents/content.hpf', '"목차": 어떤 파일이 있나'], 'n5')
    s += node(610, 140, 280, 76, ['BinData/image1.jpg …', '사진 원본 (JPG·PNG)', '그림 칸이 번호로 가리킴'], 'n3')
    s += node(610, 240, 280, 60, ['Preview/PrvText.txt', '미리보기 글 (앞 1024자)'], 'n5')
    s += edge([(420, 205), (420, 155)], 'charPrIDRef="3" → 3번 글자 모양', 432, 185, dashed=True, anchor='start')
    s += edge([(570, 255), (610, 195)], None, dashed=True)
    s += note(30, 340, ['한글은 header.xml(사전)에서 번호로 모양을 찾아 section0.xml(글)을 꾸밉니다.',
                        '그래서 두 파일의 번호가 서로 맞아야 열립니다. html2hwpx.py 가 이 번호 맞추기를 맡습니다.'])
    return svg(920, 420, s, 'HWPX 내부: ZIP 안의 mimetype, header.xml, section0.xml, BinData')


def sequence():
    lanes = [('브라우저', 100), ('app.py', 290), ('convert.py', 500), ('변환기', 690), ('디스크', 850)]
    X = dict((n, x) for n, x in lanes)
    s = ''
    for n, x in lanes:
        s += node(x - 65, 10, 130, 38, [n], 'n1' if n == 'app.py' else 'n5')
        s += f'<line x1="{x}" y1="48" x2="{x}" y2="640" class="life"/>'

    def arrow(a, b, y, label, dashed=False):
        xa, xb = X[a], X[b]
        pts = [(xa, y), (xb, y)]
        return edge(pts, label, (xa + xb) / 2, y - 7, dashed=dashed)

    def selfloop(a, y, label):
        x = X[a]
        return (edge([(x, y), (x + 46, y), (x + 46, y + 16), (x, y + 16)], None)
                + f'<text x="{x + 56}" y="{y + 12}" class="el" text-anchor="start">{esc(label)}</text>')
    s += arrow('브라우저', 'app.py', 90, '① 파일 올리기 (100MB 이하)')
    s += selfloop('app.py', 120, '② 임시 파일로 써서 형식 판별 (inspect_upload)')
    s += arrow('app.py', '브라우저', 182, '③ 판별 결과·근거·고를 수 있는 형식 표시', dashed=True)
    s += arrow('브라우저', 'app.py', 226, '④ [변환] 버튼 클릭')
    s += selfloop('app.py', 252, '⑤ 자리 3칸 중 하나 잡기 (없으면 60초까지 대기)')
    s += arrow('app.py', '디스크', 326, '⑥ 임시 폴더에 input 저장')
    s += arrow('app.py', 'convert.py', 372, '⑦ 새 프로세스: convert.py input output (120초 제한)')
    s += arrow('convert.py', '변환기', 418, '⑧ 형식 판별 → 변환 길 → 변환기 호출')
    s += arrow('변환기', '디스크', 464, '⑨ output 파일 쓰기 (압축·그림 한도 검사)')
    s += arrow('convert.py', 'app.py', 510, '⑩ 종료 코드 0 (실패면 오류 한 줄)', dashed=True)
    s += arrow('app.py', '디스크', 556, '⑪ output 읽고 · 임시 폴더 지우고 · 장부 한 줄')
    s += arrow('app.py', '브라우저', 602, '⑫ 완료 표시 + 다운로드 버튼', dashed=True)
    return svg(920, 660, s, '요청 한 건의 상세 순서도: 브라우저, app.py, convert.py, 변환기, 디스크 사이의 12단계')


def layout_v2():
    s = ''
    s += group(10, 10, 900, 400, 'File-conversation/ (프로젝트 루트)', 'g1')
    s += node(30, 55, 190, 56, ['samples/', '원본 샘플 3개'], 'n5')
    s += node(30, 128, 190, 56, ['results/', '변환 결과물 V0 ~ V4'], 'n5')
    s += node(30, 201, 190, 56, ['docs/', '설명서·계획서·이 보고서'], 'n5')
    s += node(30, 274, 190, 70, ['corpus/ (새로)', '외부 점검용 문서 32건', '공유·커밋 안 함'], 'n3')
    s += note(30, 365, ['tools/ · langfuse/ ·', '.env · .venv 는 그대로'], cls='ts')
    s += group(250, 55, 640, 340, 'versions/', 'g2')
    s += node(275, 105, 270, 120, ['V1_2026-10-07_발표버전', '발표 때의 코드·설정·문서', '보관용 — 수정하지 않음', '16개 파일, 해시로 확인'], 'n5')
    s += node(600, 105, 270, 260, ['V2  ← 여기서만 개발', 'app.py · convert.py', 'hwp2html · hwpx2html · html2hwpx', 'approval.py (결재선, 새로)', 'check_corpus.py (일반화 점검, 새로)',
                                  'fonts.conf (PDF 글꼴 대응, 새로)', 'Dockerfile · compose.yaml', 'test_hwpx_roundtrip.py'], 'n2')
    s += edge([(545, 165), (600, 165)], '복사해서 시작', 572, 150)
    s += note(275, 262, ['V2 의 코드는 samples/ · results/ 를', '위로 두 단계 올라가 읽는다.', 'V2 를 마치면 versions/V2_… 보관본을 남긴다.'])
    s += note(275, 335, ['실행(V2 폴더에서): docker compose up -d --build'], cls='ts')
    return svg(920, 430, s, '폴더 구조: V1 은 보관, V2 에서만 개발, 루트에는 samples·results·docs·corpus')


def routes_v2():
    s = ''
    s += node(20, 120, 150, 90, ['HWP', '.hwp'], 'n3')
    s += node(260, 120, 150, 90, ['HTML', '.html'], 'n1')
    s += node(500, 120, 150, 90, ['HWPX', '.hwpx'], 'n2')
    s += node(740, 120, 150, 90, ['PDF (새로)', '.pdf'], 'n4')
    s += edge([(170, 150), (260, 150)], 'hwp2html', 215, 142)
    s += edge([(410, 150), (500, 150)], 'html2hwpx', 455, 142)
    s += edge([(500, 185), (410, 185)], 'hwpx2html', 455, 205)
    s += edge([(335, 120), (335, 62), (815, 62), (815, 120)], 'html → pdf : WeasyPrint (새로)', 575, 54)
    s += edge([(95, 210), (95, 262), (575, 262), (575, 210)], 'hwp → hwpx : HTML 을 거쳐 한 번에', 335, 282)
    s += node(190, 305, 540, 50, ['결재선(옵션): 어느 길이든 HTML 에 표를 끼운 뒤 변환', 'hwp·hwpx → pdf 도 HTML 을 거친다'], 'n3')
    return svg(920, 370, s, '변환 길 V2: PDF 가 추가되고, 결재선 옵션이 모든 길 앞에 붙는다')


def bars(before, after):
    """before/after = (ok, warn, bad)"""
    s = ''
    total = sum(before); w = 620; x0 = 150
    def row(y, label, vals):
        out = f'<text x="10" y="{y + 25}" class="tb">{esc(label)}</text>'; x = x0
        for v, cls, name in zip(vals, ('bar-ok', 'bar-warn', 'bar-bad'), ('이상 없음', '주의', '실패')):
            ww = w * v / total
            if v: out += f'<rect x="{x}" y="{y}" width="{ww}" height="38" class="{cls}"/><text x="{x + ww / 2}" y="{y + 25}" text-anchor="middle" class="bt">{v}</text>'
            x += ww
        return out
    s += row(20, '고치기 전', before) + row(80, '고친 뒤', after)
    s += (f'<rect x="{x0}" y="150" width="18" height="14" class="bar-ok"/><text x="{x0 + 24}" y="162" class="ts">이상 없음</text>'
          f'<rect x="{x0 + 120}" y="150" width="18" height="14" class="bar-warn"/><text x="{x0 + 144}" y="162" class="ts">주의(변환은 됨, 확인 필요)</text>'
          f'<rect x="{x0 + 360}" y="150" width="18" height="14" class="bar-bad"/><text x="{x0 + 384}" y="162" class="ts">실패(변환 불가)</text>')
    return svg(800, 180, s, f'점검 32건 결과: 고치기 전 {before}, 고친 뒤 {after}')

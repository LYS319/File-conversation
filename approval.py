"""결재선: 문서 맨 위 오른쪽에 '담당·검토·확인·승인' 같은 칸이 있는 표를 끼워 넣는다.
변환 전의 HTML 에 표를 넣는 방식이라 HTML 출력에도, html2hwpx 를 거친 HWPX 출력에도 똑같이 나온다.
    add(html_text, ('담당', '검토', '확인', '승인'))  ->  표가 들어간 html_text

오른쪽 정렬은 정렬 기능에 기대지 않고 구조로 만든다: 본문 폭 전체 표의 왼쪽을 테두리 없는 빈 칸(여백 칸)으로 채우고 오른쪽에 결재 칸을 둔다.
(떠 있는 표의 horzAlign·글자처럼 놓은 표의 문단 정렬은 렌더러마다 달라서 믿을 수 없었다.)"""
import html as H
import re
from pathlib import Path

DEFAULT = ('담당', '검토', '확인', '승인')
HEAD_MM, SIGN_MM = 8, 16                       # 이름칸 높이 · 서명칸 높이(mm)
FONT = "'함초롬바탕'"
BORDER = 'border:0.12mm solid #000000'


def labels_from(text):
    """'담당, 검토 ,승인' -> ('담당','검토','승인'). 비면 None(결재선 없음). 칸은 최대 8개."""
    out = tuple(s.strip() for s in re.split(r'[,，\n]', text or '') if s.strip())
    return out[:8] or None


def table(labels=DEFAULT):
    n = len(labels)
    pct = min(13, 90 // n)                     # 결재 칸 하나가 본문 폭에서 차지하는 비율(%). A4 본문 폭이면 13% ≈ 22mm
    spacer = 100 - pct * n                     # 왼쪽 빈 칸
    cell = lambda inner, h, bg='': (f'<td style="width:{pct}%;height:{h}mm;padding:1pt 2pt;vertical-align:middle;{BORDER}{bg}">'
                                    f'<p style="text-align:center;font-size:10pt;font-family:{FONT}">{inner}</p></td>')
    head = ''.join(cell(H.escape(s, quote=False), HEAD_MM, ';background-color:#D6D6D6') for s in labels)
    sign = ''.join(cell('', SIGN_MM) for _ in labels)
    cols = f'<col style="width:{spacer}%">' + ''.join(f'<col style="width:{pct}%">' for _ in labels)
    blank = f'<td rowspan="2" style="width:{spacer}%;border:none"><p style="font-size:10pt;font-family:{FONT}"></p></td>'
    return (f'<table class="approval" style="border-collapse:collapse;table-layout:fixed;width:100%;margin:0 0 8pt 0">'
            f'<colgroup>{cols}</colgroup><tr>{blank}{head}</tr><tr>{sign}</tr></table>')


def add(html_text, labels=DEFAULT):
    """문서 본문 맨 앞(첫 <div class="page"> 안, 없으면 <body> 바로 뒤)에 결재선 표를 넣는다."""
    t = table(labels)
    m = re.search(r'<div class="page"[^>]*>', html_text) or re.search(r'<body[^>]*>', html_text, re.I)
    if not m: return t + html_text                      # ponytail: 본문 표지가 없는 조각 HTML 은 맨 앞에 그냥 붙인다
    return html_text[:m.end()] + t + html_text[m.end():]


def add_to_file(path, labels=DEFAULT):
    p = Path(path)
    p.write_text(add(p.read_text(encoding='utf-8'), labels), encoding='utf-8')

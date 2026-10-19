"""HTML -> PDF 평가용 기준 PDF 만들기(윈도 호스트에서): corpus/html/in/*.html 을 Edge 의 '인쇄'(headless --print-to-pdf)로 찍어 corpus/html/pdf/ 에 둔다.
    python make_html_refs.py [--force]       기준 = '브라우저가 이 HTML 을 인쇄하면 이렇게 나온다'(한컴 정답이 아니다). manifest.json 도 같이 쓴다.
Edge 는 이 PC 의 진짜 글꼴(맑은 고딕 등)을 쓰고 우리는 나눔 글꼴이라 글꼴 차이가 섞인다 — 절대 점수보다 회귀·개선 비교용이다. 네트워크는 쓰지 않는다(오프라인)."""
import json, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]; IN = ROOT / 'corpus' / 'html' / 'in'; OUT = ROOT / 'corpus' / 'html' / 'pdf'
EDGE = next((p for p in (r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', r'C:\Program Files\Microsoft\Edge\Application\msedge.exe') if Path(p).exists()), None)
if not EDGE: sys.exit('Edge 를 못 찾음')
OUT.mkdir(exist_ok=True); force = '--force' in sys.argv; man = []
for f in sorted(IN.glob('*.html')):
    pdf = OUT / (f.stem + '.pdf')
    if force or not pdf.exists():
        with tempfile.TemporaryDirectory() as prof:      # 임시 프로필(사용자 설정·확장 영향 없음)
            subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--no-sandbox', '--no-pdf-header-footer', f'--user-data-dir={prof}', f'--print-to-pdf={pdf}', f.as_uri()], capture_output=True, timeout=120)
        print(f.name, '->', 'OK' if pdf.exists() else '실패')
    if pdf.exists(): man.append({'path': 'in/' + f.name, 'oracle_pdf': 'pdf/' + pdf.name})
(ROOT / 'corpus' / 'html' / 'manifest.json').write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding='utf-8'); print('manifest', len(man), '건')

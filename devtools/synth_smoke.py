"""합성 시험 문서 스모크: 한컴이 저장된 줄 없는 HWPX 를 열어 줄을 새로 계산하는지, 우리 줄 나눔기와 얼마나 맞는지 처음 확인한다. 출력: corpus/synth/smoke.hwpx + smoke.json"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'devtools'))
from synth_hwpx import build, TEXT_W
ko = '한글 문서의 줄 나눔은 글자 폭과 공백 폭 그리고 문단 모양에 따라 정해집니다. 우리 변환기는 이 규칙을 따라 줄을 끊어야 합니다. '
en = 'The quick brown fox jumps over the lazy dog while 12,345 people watched (carefully) from far away, 2026-10-14. '
mix = '2026년 10월 14일(수) 09:00~12:00 서울시 중구 세종대로 110, 3층 회의실(Room 301)에서 열립니다. 문의: 02-123-4567. '
rows = []
for w in (20000, 26000, 31000):
    for ku in (1, 0):
        for name, t in (('ko', ko * 3), ('en', en * 3), ('mix', mix * 3)):
            rows.append(dict(text=t, face='함초롬바탕', size=10, ku=ku, right=TEXT_W - w, name='%s w%d ku%d' % (name, w, ku)))
for ch in '가abW0.':
    rows.append(dict(text=ch * 60, face='함초롬바탕', size=10, ku=1, right=TEXT_W - 20000, name='char %s' % ch))
out = ROOT / 'corpus' / 'synth'; out.mkdir(exist_ok=True)
build(rows, str(out / 'smoke.hwpx')); (out / 'smoke.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
print('문단', len(rows), '->', out / 'smoke.hwpx')

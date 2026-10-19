"""rhwp(비교용 엔진)와 우리 변환기(V2 아침·V3 지금)를 한 장의 HTML 로 비교한다(요약표·막대·문서별 산점도·쪽 수 표·한컴/rhwp/우리 쪽 그림).
    python devtools/compare_viz.py 태그 [출력폴더]      # 태그 = 우리 평가 폴더 꼬리표(corpus/_eval/<세트>_<태그>), 예: v3d
기준: 한컴 PDF. rhwp = corpus/_eval/<세트>_rhwp, V2 아침 = <세트>_w4(2026-10-14 오후), V3 아침 = <세트>_v3c(10-14 밤).
그림은 공개 코퍼스(rhwp2) 문서만 넣는다(사용자 문서는 숫자만; corpus/no_external.txt)."""
import base64, io, json, os, statistics, sys
from pathlib import Path
import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]; EV = ROOT / 'corpus' / '_eval'
TAG = sys.argv[1]; OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'results' / 'V16_rhwp_비교시각화_2026-10-15'
SETS = [('user', '사용자 8건(독립 증거)'), ('rhwp', '공개 20건'), ('rhwp2', '공개 102건')]
RUNS = [('rhwp', 'rhwp v0.8.7', '#8e7cc3', lambda s: f'{s}_rhwp'), ('v2', 'V2 (10-14 오후)', '#999999', lambda s: f'{s}_w4'),
        ('v3a', 'V3 (10-14 밤)', '#6fa8dc', lambda s: f'{s}_v3c'), ('now', f'V3 지금({TAG})', '#e06666', lambda s: f'{s}_{TAG}')]


def load(run, s):
    f = EV / run(s) / 'eval.json'
    return {d['doc']: d for d in json.loads(f.read_text(encoding='utf-8'))} if f.exists() else {}


def agg(rows):
    ok = [r for r in rows if r.get('ours') is not None and not r.get('suspect')]
    dy = [r['dy'] for r in ok if r.get('dy') is not None]; ink = [r['ink'] for r in ok if r.get('ink') is not None]; sec = [r['sec'] for r in ok if r.get('sec') is not None]
    return dict(n=len(ok), same=sum(1 for r in ok if r['ours'] == r['ref']), err=sum(abs(r['ours'] - r['ref']) for r in ok), ink=statistics.mean(ink) if ink else 0, dy=statistics.mean(dy) if dy else 0, sec=statistics.median(sec) if sec else 0)


DATA = {s: {k: load(fn, s) for k, _, _, fn in RUNS} for s, _ in SETS}
# 엔진마다 '정답 의심'·실패로 빼는 문서가 달라, 모든 엔진에서 유효한 문서만 모아 같은 문서 집합으로 비교한다
COMMON = {s: {d for d in DATA[s]['now'] if all(d in DATA[s][k] and DATA[s][k][d].get('ours') is not None and not DATA[s][k][d].get('suspect') for k, *_ in RUNS if DATA[s][k])} for s, _ in SETS}
A = {s: {k: agg([r for d, r in DATA[s][k].items() if d in COMMON[s]]) for k, *_ in RUNS} for s, _ in SETS}


def svg_bars(title, key, fmt, higher_better=True, lo=None):
    W, H, pad = 560, 230, 40; vals = [[A[s][k][key] for k, *_ in RUNS] for s, _ in SETS]
    mx = max(max(v) for v in vals) * 1.15 or 1; mn = lo if lo is not None else 0
    gw = (W - pad) / len(SETS); bw = gw / (len(RUNS) + 1)
    o = [f'<svg viewBox="0 0 {W} {H}" class="chart"><text x="{W/2}" y="16" text-anchor="middle" class="ct">{title}</text>']
    for gi, (s, nm) in enumerate(SETS):
        for ri, (k, lab, col, _) in enumerate(RUNS):
            v = vals[gi][ri]; h = (v - mn) / (mx - mn) * (H - 70); x = pad + gi * gw + bw * (ri + .5); y = H - 30 - h
            o.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw*.9:.1f}" height="{h:.1f}" fill="{col}"><title>{nm} · {lab}: {fmt(v)}</title></rect><text x="{x+bw*.45:.1f}" y="{y-3:.1f}" text-anchor="middle" class="bv">{fmt(v)}</text>')
        o.append(f'<text x="{pad + gi*gw + gw/2:.1f}" y="{H-12}" text-anchor="middle" class="bl">{nm}</text>')
    return ''.join(o) + '</svg>'


def svg_scatter(s='rhwp2'):
    a, b = DATA[s]['rhwp'], DATA[s]['now']; pts = [(a[d]['ink'], b[d]['ink'], d) for d in a if d in b and not a[d].get('suspect') and a[d].get('ink') is not None and b[d].get('ink') is not None and b[d].get('ours') is not None]
    W = 360; o = [f'<svg viewBox="0 0 {W+50} {W+50}" class="chart sq"><line x1="40" y1="{W+10}" x2="{W+40}" y2="10" stroke="#bbb" stroke-dasharray="4"/>']
    for x, y, d in pts:
        o.append(f'<circle cx="{40 + x*W:.1f}" cy="{W+10 - y*W:.1f}" r="3.6" fill="{"#e06666" if y > x + .02 else "#8e7cc3" if y < x - .02 else "#999"}" fill-opacity=".75"><title>{d}: rhwp {x:.2f} · 우리 {y:.2f}</title></circle>')
    win = sum(1 for x, y, _ in pts if y > x + .02); lose = sum(1 for x, y, _ in pts if y < x - .02)
    o.append(f'<text x="{W/2+40}" y="{W+40}" text-anchor="middle" class="bl">rhwp 모양 유사도 →</text><text x="12" y="{W/2}" class="bl" transform="rotate(-90 12 {W/2})" text-anchor="middle">우리 유사도 →</text></svg>')
    return ''.join(o), win, lose, len(pts)


def table_summary():
    r = ['<table class="t"><tr><th>세트</th><th>엔진</th><th>쪽 일치</th><th>쪽 오차 합</th><th>모양 유사도</th><th>글 위치 dy(pt)</th><th>변환 시간(중앙, 초)</th></tr>']
    for s, nm in SETS:
        for k, lab, col, _ in RUNS:
            m = A[s][k]
            if not m['n']: continue
            r.append(f'<tr><td>{nm}</td><td><span class="dot" style="background:{col}"></span>{lab}</td><td>{m["same"]}/{m["n"]}</td><td>{m["err"]}</td><td>{m["ink"]:.3f}</td><td>{m["dy"]:.1f}</td><td>{m["sec"]:.1f}</td></tr>')
    return ''.join(r) + '</table>'


def table_pages(s='rhwp2'):
    rr, now = DATA[s]['rhwp'], DATA[s]['now']; v2 = DATA[s]['v2']; rows = []
    for d, b in now.items():
        a = rr.get(d)
        if not a or b.get('suspect') or b.get('ours') is None or a.get('ours') is None: continue
        if a['ours'] != a['ref'] or b['ours'] != b['ref']: rows.append((max(abs(a['ours'] - a['ref']), abs(b['ours'] - b['ref'])), d, a, b, v2.get(d)))
    rows.sort(key=lambda t: -t[0]); cls = lambda x, ref: 'ok' if x == ref else 'bad'
    o = ['<table class="t"><tr><th>문서</th><th>한컴</th><th>rhwp</th><th>V2(아침)</th><th>V3 지금</th></tr>']
    for _, d, a, b, c in rows:
        o.append(f'<tr><td>{d}</td><td>{b["ref"]}</td><td class="{cls(a["ours"], a["ref"])}">{a["ours"]}</td><td class="{cls(c["ours"], c["ref"]) if c and c.get("ours") else ""}">{c["ours"] if c and c.get("ours") else "-"}</td><td class="{cls(b["ours"], b["ref"])}">{b["ours"]}</td></tr>')
    return ''.join(o) + '</table>', len(rows)


def page_img(pdf, pno, w=300):
    try:
        d = pymupdf.open(str(pdf)); pg = d[min(pno, len(d)) - 1]; z = w / pg.rect.width
        pm = pg.get_pixmap(matrix=pymupdf.Matrix(z, z)); im = Image.open(io.BytesIO(pm.tobytes('png'))).convert('RGB')
        buf = io.BytesIO(); im.save(buf, 'JPEG', quality=72); return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode(), len(d)
    except Exception:
        return '', 0


def figures():
    man = [m for m in json.loads((ROOT / 'corpus' / 'rhwp2' / 'manifest.json').read_text(encoding='utf-8')) if 'oracle_pdf' in m]
    want = [('multi-table-002', 2, '칸 안 여백 비트 수정'), ('sample1-repro', 10, '큰 표 행 나눔'), ('rowbreak-problem-pages', 9, '큰 표 행 나눔'), ('2022년 국립국어원 업무계획', 5, '쪽 끝 판정'),
            ('hwpx_sample2', 6, '큰 표 행 나눔'), ('pr-1674', 3, '큰 표 행 나눔(남음)'), ('exam_math', 5, '수식·시험지(rhwp 우세)'), ('text-align-2', 1, '글 정렬')]
    o = []
    for stem, pno, why in want:
        for i, m in enumerate(man):
            if Path(m['path']).stem != stem: continue
            nm = f'{i:03d}_{stem[:40]}.pdf'; srcs = [('한컴', ROOT / 'corpus' / 'rhwp2' / m['oracle_pdf']), ('rhwp', EV / 'rhwp2_rhwp' / nm), (f'V3 {TAG}', EV / f'rhwp2_{TAG}' / nm)]
            cells = []
            for lab, f in srcs:
                src, n = page_img(f, pno); cells.append(f'<figure><img src="{src}"><figcaption>{lab} · {n}쪽</figcaption></figure>')
            o.append(f'<div class="fig"><h4>{stem} — {pno}쪽 <span class="why">{why}</span></h4><div class="row">{"".join(cells)}</div></div>'); break
    return ''.join(o)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sc, win, lose, n = svg_scatter(); tp, ntp = table_pages()
    css = ('body{font-family:"Malgun Gothic","Noto Sans KR",sans-serif;margin:24px auto;max-width:1100px;padding:0 16px;color:#222;background:#fff}h1{font-size:22px}h2{font-size:17px;margin-top:34px;border-bottom:2px solid #eee;padding-bottom:4px}'
           '.t{border-collapse:collapse;font-size:13px;margin:8px 0}.t td,.t th{border:1px solid #ddd;padding:4px 9px;text-align:right}.t td:first-child,.t th:first-child,.t td:nth-child(2){text-align:left}.t th{background:#f4f4f4}'
           '.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}.chart{width:100%;max-width:560px;background:#fafafa;border:1px solid #eee}.sq{max-width:420px}.ct{font-size:13px;font-weight:700}.bv{font-size:9px}.bl{font-size:11px}'
           '.grid{display:flex;flex-wrap:wrap;gap:14px}.ok{background:#e6f4ea}.bad{background:#fde8e8}.fig{margin:14px 0}.row{display:flex;gap:10px}figure{margin:0;text-align:center}figure img{width:300px;border:1px solid #ccc}figcaption{font-size:12px}.why{font-size:12px;color:#888;font-weight:400}'
           '.note{font-size:12px;color:#666}@media(max-width:700px){.row{flex-direction:column}}')
    html = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>rhwp 대 우리 변환기 비교</title><style>{css}</style></head><body>
<h1>rhwp 대 우리 변환기 — 한컴 PDF 기준 비교 (2026-10-15)</h1>
<p class="note">정답 = 한컴이 낸 PDF. rhwp = 비교용 엔진 rhwp v0.8.7(PDF 내보내기). 우리 = V2(10-14 오후)·V3(10-14 밤·{TAG}). 같은 평가기(eval_layout.py)로 쪽 수·모양 유사도(그림 대조)·글 위치(dy)를 쟀다. 사용자 8건은 숫자만 싣는다. 엔진마다 '정답 의심'·실패로 빼는 문서가 달라, <b>모든 엔진에서 유효한 문서만</b> 같은 집합으로 비교한다(공개 102건 세트는 {len(COMMON['rhwp2'])}건).</p>
<h2>한눈에 보기</h2>{table_summary()}
<div class="grid">{svg_bars('쪽 수 일치 문서 수', 'same', lambda v: f'{v:.0f}')}{svg_bars('모양 유사도(평균, 클수록 좋음)', 'ink', lambda v: f'{v:.2f}')}</div>
<h2>문서별 모양 유사도: rhwp 대 우리 (공개 102건)</h2><div class="grid">{sc}<div><p>점 하나 = 문서 하나. <b style="color:#e06666">빨강</b> {win}건은 우리가 rhwp 보다 0.02 넘게 높고, <b style="color:#8e7cc3">보라</b> {lose}건은 rhwp 가 높다. 나머지 {n-win-lose}건은 비슷하다(대각선 근처).</p>
<p class="note">rhwp 는 한컴 글꼴 폭표를 쓰는 엔진이라 평균 유사도는 아직 크게 앞선다. 우리는 쪽 수 일치와 글 위치(dy)에서 어디까지 따라왔는지를 본다.</p></div></div>
<h2>쪽 수가 한컴과 다른 문서 ({ntp}건, 공개 102건)</h2>{tp}<p class="note">초록 = 한컴과 같은 쪽 수, 빨강 = 다름.</p>
<h2>같은 쪽을 나란히 (공개 문서만)</h2>{figures()}
</body></html>'''
    (OUT / 'index.html').write_text(html, encoding='utf-8'); print('저장', OUT / 'index.html', len(html) // 1024, 'KB')


if __name__ == '__main__': main()

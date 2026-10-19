"""줄 끊김 재현에서 '우리가 좁게 잼'(한컴은 끊었는데 우리는 다음 낱말도 들어간다고 본 줄)의 원인 탐색: 조건별 분포와 예를 낸다.
    PYTHONUTF8=1 python devtools/linebreak_diag.py [문서 부분이름]"""
import collections, glob, os, statistics as st, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'devtools')); sys.path.insert(0, str(ROOT / 'core')); sys.path.insert(0, str(ROOT))
import linebreak_eval as L
P, H, M = L.P, L.H, L.M
model = L.Model('half', 'glyph')
rows = []      # (문서, 판정, 여유(글자폭), 글꼴, 정렬, 자간, 장평, 크기, 줄 글자수, 한글 비율)
for f in sorted(glob.glob(str(ROOT / 'corpus' / 'rhwp*' / '**' / '*.hwp'), recursive=True)):
    if len(sys.argv) > 1 and sys.argv[1] not in f: continue
    if open(f, 'rb').read(8) != L.OLE or os.path.getsize(f) > 8_000_000: continue
    try: ps = [p for p in P.iter_paragraphs(f) if len(p.lines) >= 2]
    except Exception: continue
    for p in ps:
        cs = [H.charshapes[k] for k in p.sid]; W = [model.width(c, s) for c, s in zip(p.text, cs)]; cb = bool(p.shape['bw'])
        for k in range(len(p.lines) - 1):
            a, b = L.idx_of(p, p.lines[k]['pos']), L.idx_of(p, p.lines[k + 1]['pos'])
            if b <= a or b >= len(p.text): continue
            seg = p.text[a:b]
            if '\n' in seg[:-1] or '\t' in seg: continue
            e = len(seg.rstrip(' ')) + a; lw = sum(W[a:e]); av = p.lines[k]['w']
            j = e
            while j < len(p.text) and p.text[j] == ' ': j += 1
            nw = L.word_end(p.text, j, cb); over = lw + sum(W[e:j]) + sum(W[j:nw])
            cw = st.mean(W[a:e]) if e > a else 1
            c0 = cs[a]; Lg = c0['langs'][0]
            hang = sum(1 for ch in seg if H.lang_of(ch) == 0) / max(1, len(seg))
            rows.append((os.path.basename(f), 'ok' if lw <= av + 1 and over > av - 1 else 'wide' if lw > av + 1 else 'narrow', (av - over) / cw, (av - lw) / cw, Lg['face'], p.shape['align'], Lg['spacing'], Lg['ratio'], c0['size'], e - a, hang, cb, p.lines[k]['x'], av, p.shape['indent'], p.shape['left'], p.shape['right']))
nar = [r for r in rows if r[1] == 'narrow']; ok = [r for r in rows if r[1] == 'ok']
print('줄', len(rows), ' narrow', len(nar), ' ok', len(ok))
def table(title, key):
    c, n = collections.Counter(key(r) for r in rows), collections.Counter(key(r) for r in nar)
    print('\n--', title)
    for k, v in sorted(c.items(), key=lambda kv: -kv[1])[:12]:
        d = [r[2] for r in nar if key(r) == k]
        print('  %-26s 줄 %5d  좁게 잼 %5.1f%%  (좁게 잰 줄의 초과 폭 중앙값 %s글자)' % (str(k)[:26], v, 100 * n[k] / v, '%.2f' % st.median(d) if d else '-'))
table('정렬(0 양쪽·1 왼·2 오른·3 가운데·4 배분·5 나눔)', lambda r: r[5])
table('글자 단위 줄 나눔(bw)', lambda r: r[11])
table('글꼴', lambda r: r[4])
table('자간(%)', lambda r: r[6])
table('장평(%)', lambda r: r[7])
table('한글 비율(구간)', lambda r: round(r[10], 1))
dd = sorted(r[2] for r in nar); print('\n좁게 잰 줄: 다음 낱말을 붙여도 남는 여유(글자 폭 단위) 25%% %.2f 중앙값 %.2f 75%% %.2f' % (dd[len(dd) // 4], st.median(dd), dd[3 * len(dd) // 4]))

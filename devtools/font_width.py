"""글꼴별 글자 폭 차이 측정: 한컴 PDF 의 낱말 폭 대 우리 PDF 의 같은 낱말 폭(같은 쪽·같은 줄에서 한 번만 나오는 낱말)의 비율을, 한컴 PDF 에 쓰인 글꼴 이름별로 모은다.
비율 W한컴/W우리 > 1 이면 우리 글꼴이 좁다. 결과는 글꼴별 폭 보정 계수(글자마다 더할 letter-spacing)를 정하는 근거다.
    python font_width.py jobs.json out.json     (component_diff 와 같은 jobs.json: name, oracle, nup, ours)"""
import collections, json, statistics, sys, os
import pymupdf
sys.path.insert(0, os.path.dirname(__file__))
from eval_layout import norm


def words_with_font(page, clip=None, k=1.0, x0=0.0):
    out = []
    for b in page.get_text('rawdict', clip=clip)['blocks']:
        for l in b.get('lines', []):
            for s in l['spans']:
                cur = []
                for ch in s['chars'] + [dict(c=' ', bbox=(0, 0, 0, 0))]:
                    if ch['c'].strip() and ch['c'] != ' ': cur.append(ch)
                    elif cur:
                        t = norm(''.join(c['c'] for c in cur))
                        if len(t) >= 2: out.append((t, (cur[0]['bbox'][0] - x0) * k, (cur[0]['bbox'][1]) * k, (cur[-1]['bbox'][2] - cur[0]['bbox'][0]) * k, s['font'], s['size'] * k))
                        cur = []
    return out


def page_words(doc, i, nup):
    if nup == 1: return words_with_font(doc[i])
    pg = doc[i // nup]; w = pg.rect.width / nup; r = pymupdf.Rect(w * (i % nup), 0, w * (i % nup + 1), pg.rect.height)
    return words_with_font(pg, clip=r, k=1 / 0.7071, x0=r.x0)


def main(jobs, out):
    by = collections.defaultdict(list)       # (한컴 글꼴, 우리 글꼴) -> [(비율, 글자 수, 크기)]
    for j in jobs:
        ref, ours = pymupdf.open(j['oracle']), pymupdf.open(j['ours']); nup = j.get('nup', 1)
        n = min(len(ref) * nup, len(ours), 6)
        for p in range(n):
            a, b = collections.defaultdict(list), collections.defaultdict(list)
            for w in page_words(ref, p, nup): a[w[0]].append(w)
            for w in page_words(ours, p, 1): b[w[0]].append(w)
            for t, v in a.items():
                if len(v) == 1 and len(b.get(t, ())) == 1:
                    h, o = v[0], b[t][0]
                    if abs(h[2] - o[2]) < 8 and o[3] > 0 and h[3] > 0 and abs(h[5] - o[5]) < 1.5:      # 같은 줄, 같은 크기만
                        by[(h[4].split('+')[-1], o[4].split('+')[-1])].append((h[3] / o[3], len(t), h[5]))
    res = []
    for (hf, of), v in by.items():
        if len(v) < 8: continue
        r = [x[0] for x in v]; med = statistics.median(r)
        # 글자당 보정량(em): (W한컴 - W우리) / (글자 수 × 크기). 비율의 중앙값으로 근사
        dem = statistics.median((x[0] - 1) * 1.0 for x in v)
        res.append(dict(hancom=hf, ours=of, n=len(v), ratio=round(med, 3), p10=round(sorted(r)[len(r) // 10], 3), p90=round(sorted(r)[len(r) * 9 // 10], 3)))
    res.sort(key=lambda x: -x['n'])
    json.dump(res, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('한컴 글꼴 | 우리 글꼴 | 낱말 수 | 폭 비율(한컴/우리) 중앙값 [p10, p90]')
    for r in res[:30]: print(f"{r['hancom'][:28]} | {r['ours'][:24]} | {r['n']} | {r['ratio']} [{r['p10']}, {r['p90']}]")


if __name__ == '__main__':
    main(json.load(open(sys.argv[1], encoding='utf-8')), sys.argv[2])

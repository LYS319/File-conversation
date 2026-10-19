"""요소 종류별 오차 분해: 한컴 PDF 의 낱말 위치를 기준으로 우리 PDF·rhwp PDF 가 요소 종류(표 칸 안 / 본문 / 머리말·꼬리말)별로 얼마나 어긋나는지 잰다.
요소 종류는 rhwp 의 render tree(`export-render-tree`, 문서 구조 + 위치 JSON)에서 한컴 PDF 낱말의 중심점이 든 가장 안쪽 노드로 정한다.
"누가 어느 부분에서 더 낫나"를 정해, 우리 코드를 고칠지 rhwp 규칙을 가져올지 고르는 근거로 쓴다. 컨테이너(pdftest:wp + /x/rhwp)에서:
    python component_diff.py jobs.json out.json
jobs.json: [{"name","src"(hwp 경로),"oracle"(한컴 PDF),"nup","ours"(우리 PDF),"rhwp"(rhwp PDF)}, ...]"""
import collections, json, statistics, subprocess, sys, tempfile, os, glob
import pymupdf
sys.path.insert(0, os.path.dirname(__file__))
from eval_layout import Pages, Plain


def tree_nodes(src, nup_pages):
    d = tempfile.mkdtemp(dir='/tmp')
    subprocess.run(['/x/rhwp', 'export-render-tree', src, '-o', d], capture_output=True, timeout=300)
    pages = []
    for f in sorted(glob.glob(d + '/render_tree_*.json')):
        flat = []
        def walk(n, anc):
            b = n.get('bbox'); t = n.get('type')
            if b and t in ('Cell', 'Header', 'Footer', 'Body', 'TextLine'): flat.append((t, b['x'] * .75, b['y'] * .75, (b['x'] + b['w']) * .75, (b['y'] + b['h']) * .75, len(anc)))
            for c in n.get('children', []): walk(c, anc + [t])
        walk(json.load(open(f, encoding='utf-8')), []); pages.append(flat)
    return pages


def kind(flat, x, y):
    best = None
    for t, x0, y0, x1, y1, depth in flat:
        if t == 'TextLine' or not (x0 - 1 <= x <= x1 + 1 and y0 - 1 <= y <= y1 + 1): continue
        if best is None or depth > best[1]: best = (t, depth)
    return {'Cell': '표 칸 안', 'Header': '머리말', 'Footer': '꼬리말', 'Body': '본문(표 밖)'}.get(best[0] if best else None, '기타')


def words(pg, i):
    c = collections.defaultdict(list)
    for w, x, y in pg.words(i): c[w].append((x, y))
    return {w: v[0] for w, v in c.items() if len(v) == 1}


def main(jobs, out, max_pages=1):
    stat = collections.defaultdict(lambda: collections.defaultdict(list)); per_doc = []; per_doc_dx = []; cur = collections.defaultdict(lambda: collections.defaultdict(list))   # per_doc_dx: 문서별 부호 있는 중앙값(체계적 오프셋인지 문서마다 다른지)
    for j in jobs:
        ref = Pages(pymupdf.open(j['oracle']), j.get('nup', 1)); ours = Plain(pymupdf.open(j['ours'])); rh = Plain(pymupdf.open(j['rhwp']))
        trees = tree_nodes(j['src'], len(ref)); n = min(len(ref), len(ours), len(rh), len(trees), max_pages); cnt = collections.Counter()
        for p in range(n):
            a, b, c = words(ref, p), words(ours, p), words(rh, p)
            for w, (x, y) in a.items():
                if w in b and w in c:
                    k = kind(trees[p], x, y + 4)
                    stat[k]['ours_dy'].append(b[w][1] - y); stat[k]['rhwp_dy'].append(c[w][1] - y)
                    stat[k]['ours_dx'].append(b[w][0] - x); stat[k]['rhwp_dx'].append(c[w][0] - x); stat[k]['y'].append(y); stat[k]['x'].append(x); cnt[k] += 1; cur[k]['dx'].append(b[w][0] - x); cur[k]['dy'].append(b[w][1] - y)
        per_doc.append((j['name'], dict(cnt))); per_doc_dx.append((j['name'], {k: (round(statistics.median(v['dx']), 1), round(statistics.median(v['dy']), 1), len(v['dx'])) for k, v in cur.items()})); cur.clear()
    res = {}
    for k, v in stat.items():
        m = lambda L: round(statistics.median(abs(x) for x in L), 1)
        lr = lambda ys, xs: statistics.linear_regression(xs, ys) if len(set(xs)) > 2 else (0, 0)
        so, io = lr(v['ours_dy'], v['y']); sx, ix = lr(v['ours_dx'], v['x'])        # 쪽 안 세로 위치(y)에 따라 오차가 쌓이는지(기울기=줄마다 누적), 일정한지(절편=여백/오프셋)
        res[k] = dict(n=len(v['ours_dy']), ours_dy=m(v['ours_dy']), rhwp_dy=m(v['rhwp_dy']), ours_dx=m(v['ours_dx']), rhwp_dx=m(v['rhwp_dx']),
                      ours_sdy=round(statistics.median(v['ours_dy']), 1), ours_sdx=round(statistics.median(v['ours_dx']), 1), dy_slope=round(so, 3), dy_icpt=round(io, 1), dx_slope=round(sx, 3))
    json.dump(dict(res=res, per_doc=per_doc, per_doc_dx=per_doc_dx), open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('요소 종류 | 낱말 수 | 세로 |dy| 우리/rhwp | 가로 |dx| 우리/rhwp | 우리 부호 dy,dx | 우리 dy 기울기(쪽 안 y 1pt 당)·절편')
    for k, r in sorted(res.items(), key=lambda kv: -kv[1]['n']): print(f"{k} | {r['n']} | {r['ours_dy']} / {r['rhwp_dy']} | {r['ours_dx']} / {r['rhwp_dx']} | {r['ours_sdy']:+}, {r['ours_sdx']:+} | {r['dy_slope']:+} · {r['dy_icpt']:+}")


if __name__ == '__main__':
    main(json.load(open(sys.argv[1], encoding='utf-8')), sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 1)

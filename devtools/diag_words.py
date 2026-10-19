"""한컴 PDF 와 우리 PDF 에서 같은 쪽에 한 번씩만 나오는 낱말의 위치를 나란히 찍는다(어긋남 원인 보기). 컨테이너에서:
    python diag_words.py 정답.pdf 우리.pdf [쪽(0부터)] [nup] [개수]
출력: 낱말 | 한컴 x,y | 우리 x,y | 차이 — y 순으로. 앞쪽 줄부터 어긋남이 커지는지(누적), 일정한지(여백)를 본다."""
import collections, sys
sys.path.insert(0, __import__('os').path.dirname(__file__))
import pymupdf
from eval_layout import Pages, Plain

ref = Pages(pymupdf.open(sys.argv[1]), int(sys.argv[4]) if len(sys.argv) > 4 else 1); our = Plain(pymupdf.open(sys.argv[2]))
pg = int(sys.argv[3]) if len(sys.argv) > 3 else 0; lim = int(sys.argv[5]) if len(sys.argv) > 5 else 40
a, b = collections.defaultdict(list), collections.defaultdict(list)
for w, x, y in ref.words(pg): a[w].append((x, y))
for w, x, y in our.words(pg): b[w].append((x, y))
rows = sorted((v[0][1], w, v[0][0], b[w][0][0], b[w][0][1]) for w, v in a.items() if len(v) == 1 and len(b.get(w, ())) == 1)
print(f'쪽 {pg}: 한컴 낱말 {len(a)} 우리 낱말 {len(b)} 짝 {len(rows)}')
for y, w, x, ox, oy in rows[:: max(1, len(rows) // lim)]:
    print(f'{w[:14]:14s} 한컴({x:6.1f},{y:6.1f}) 우리({ox:6.1f},{oy:6.1f}) dx{ox - x:+6.1f} dy{oy - y:+6.1f}')

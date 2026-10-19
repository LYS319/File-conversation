"""두 PDF 의 쪽 안 세로선(표 칸 경계) x 좌표를 나란히 찍는다 -> 표가 어디서 시작하고 칸 폭이 어떻게 다른지.
    python vlines.py 정답.pdf 우리.pdf [쪽] [nup]"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import pymupdf


def vx(pdf, pg, nup=1):
    d = pymupdf.open(pdf); p = d[pg // nup]; w = p.rect.width / nup; k = 1 / 0.7071 if nup > 1 else 1; off = w * (pg % nup)
    xs = []
    for dr in p.get_drawings():
        r = dr['rect']
        if r.width < 2.5 and r.height > 12 and off <= r.x0 < off + w: xs.append(round((r.x0 - off) * k, 1))
    return sorted(set(xs))


a = vx(sys.argv[1], int(sys.argv[3]) if len(sys.argv) > 3 else 0, int(sys.argv[4]) if len(sys.argv) > 4 else 1)
b = vx(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 0)
print('한컴 세로선 x:', a); print('우리 세로선 x:', b)

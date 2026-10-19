import sys, pymupdf
def hl(doc, n):
    ys = set()
    for d in doc[n - 1].get_drawings():
        for it in d['items']:
            if it[0] == 'l' and abs(it[1].y - it[2].y) < 0.3 and abs(it[1].x - it[2].x) > 150: ys.add(round(it[1].y, 1))
            if it[0] == 're':
                r = it[1]
                if r.width > 150 and r.height < 1.5: ys.add(round(r.y0, 1))
    return sorted(ys)
for s in sys.argv[1:]:
    f, n = s.rsplit(':', 1); y = hl(pymupdf.open(f), int(n))
    print(s.split('/')[-1], '선', len(y), '행 높이(pt):', [round(b - a, 1) for a, b in zip(y, y[1:]) if b - a > 4])

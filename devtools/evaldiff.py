import sys, re
def load(p):
    d = {}
    for l in open(p, encoding='utf-8', errors='replace'):
        c = [x.strip() for x in l.split('|')]
        if len(c) >= 13 and re.match(r'\d+/\d+', c[2]):
            try: d[c[0]] = (c[2].split()[0], float(c[-1]), float(c[7]), c[1])
            except ValueError: pass
    return d
a, b = load(sys.argv[1] + '/eval.txt'), load(sys.argv[2] + '/eval.txt')
rows = []
for k in sorted(set(a) & set(b)):
    pa, pb = a[k], b[k]
    if pa[0] != pb[0] or abs(pa[1] - pb[1]) >= 0.005: rows.append((pb[1] - pa[1], k, pa[0], pb[0], pa[1], pb[1], pa[2], pb[2]))
print('변한 문서', len(rows), '/', len(set(a) & set(b)))
for r in sorted(rows):
    gt = r[2].split('/')[1]; ok = lambda p: '✓' if p.split('/')[0] == gt else '✗'
    print(f'{r[0]:+.3f} {r[1]:55s} 쪽 {r[2]}{ok(r[2])} -> {r[3]}{ok(r[3])}  유사도 {r[4]:.3f} -> {r[5]:.3f}  dy {r[6]:.1f} -> {r[7]:.1f}')

import pymupdf, sys
for n in sys.argv[1:]:
    for tag, f in (('ours', f'/out/{n}_ours.pdf'), ('ref', f'/out/{n}_ref.pdf')):
        d = pymupdf.open(f); print(n, tag, '쪽', len(d))
        for i, pg in enumerate(d):
            if i < 2: pg.get_pixmap(matrix=pymupdf.Matrix(1.0, 1.0)).save(f'/out/{n}_{tag}_p{i+1}.png')

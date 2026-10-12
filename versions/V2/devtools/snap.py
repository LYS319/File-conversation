import json, sys, pymupdf
from pathlib import Path
IN, OUT = Path('/in'), Path('/out')
suffix = sys.argv[1]; x0, y0, x1, y1 = map(float, sys.argv[2:6])
m = next(m for m in json.loads((IN / 'manifest.json').read_text(encoding='utf-8')) if m['path'].endswith(suffix) and 'oracle_pdf' in m)
for name, f in (('ref', IN / m['oracle_pdf']), ('ours', OUT / 'diag_path_now.pdf')):
    pg = pymupdf.open(str(f))[0]
    pg.get_pixmap(matrix=pymupdf.Matrix(1.6, 1.6), clip=pymupdf.Rect(x0, y0, x1, y1)).save(str(OUT / f'snap_{name}.png'))

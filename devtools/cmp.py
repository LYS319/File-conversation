import json, subprocess, sys, pymupdf
from pathlib import Path
from PIL import Image
IN, OUT = Path('/in'), Path('/out')
suffix = sys.argv[1]; page = int(sys.argv[2]) if len(sys.argv) > 2 else 0; scale = float(sys.argv[3]) if len(sys.argv) > 3 else 0.75
m = next(m for m in json.loads((IN / 'manifest.json').read_text(encoding='utf-8')) if m['path'].endswith(suffix) and 'oracle_pdf' in m)
pdf = OUT / 'cmp_now.pdf'
r = subprocess.run([sys.executable, '/work/convert.py', str(IN / m['path']), str(pdf)], capture_output=True, text=True)
for l in r.stdout.splitlines() + r.stderr.splitlines():
    if '경고' in l or 'pages' in l or 'Error' in l: print(l[:140])
ref, ours = pymupdf.open(str(IN / m['oracle_pdf'])), pymupdf.open(str(pdf))
print('쪽 수: 한컴', len(ref), '우리', len(ours))
ims = []
for d in (ref, ours):
    pg = d[min(page, len(d) - 1)]; pm = pg.get_pixmap(matrix=pymupdf.Matrix(scale, scale)); ims.append(Image.frombytes('RGB', (pm.width, pm.height), pm.samples))
h = max(x.height for x in ims); comp = Image.new('RGB', (ims[0].width + ims[1].width + 10, h), 'white')
comp.paste(ims[0], (0, 0)); comp.paste(ims[1], (ims[0].width + 10, 0)); comp.save(OUT / 'cmp.png')

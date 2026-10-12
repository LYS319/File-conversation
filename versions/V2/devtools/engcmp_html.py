import json, weasyprint, pymupdf
from pathlib import Path
from PIL import Image, ImageOps
IN, OURS, H = Path('/in'), Path('/ours'), Path('/html')
man = [m for m in json.loads((IN / 'manifest.json').read_text(encoding='utf-8')) if 'oracle_pdf' in m]
def grid(page):
    pm = page.get_pixmap(matrix=pymupdf.Matrix(0.6, 0.6), colorspace=pymupdf.csGRAY)
    return list(ImageOps.invert(Image.frombytes('L', (pm.width, pm.height), pm.samples)).resize((40, 56), Image.BOX).getdata())
def sim(a, b):
    num = sum(min(x, y) for x, y in zip(a, b)); den = sum(max(x, y) for x, y in zip(a, b)); return num / den if den else 1.0
def score(ref, x):
    n = max(len(ref), len(x)); return sum(sim(grid(ref[i]), grid(x[i])) if i < len(ref) and i < len(x) else 0 for i in range(n)) / n
rows = []; tot = {'ours': 0, 'cli': 0}; cnt = {'ours': 0, 'cli': 0}; n = 0
for i, m in enumerate(man):
    if not m['path'].endswith('.hwp'): continue
    n += 1; stem = Path(m['path']).stem; ref = pymupdf.open(str(IN / m['oracle_pdf'])); r = {'doc': m['path'][-28:], 'ref': len(ref)}
    ours = pymupdf.open(str(OURS / f'{i:02d}_{stem}.pdf'))
    try: cli = pymupdf.open(stream=weasyprint.HTML(filename=str(H / f'd{i:02d}' / 'x.html')).write_pdf(), filetype='pdf')
    except Exception as e: cli = None
    for k, x in (('ours', ours), ('cli', cli)):
        r[k] = len(x) if x else 'ERR'; s = score(ref, x) if x else 0; r[k + '_s'] = s; tot[k] += s; cnt[k] += (x is not None and len(x) == len(ref))
    rows.append(r)
print('문서 | 한컴쪽 | 우리 HTML→PDF | hwp-cli HTML→PDF')
for r in rows: print(f"{r['doc']} | {r['ref']} | {r['ours']} {r['ours_s']:.2f} | {r['cli']} {r['cli_s']:.2f}")
print(f"평균 유사도 우리 {tot['ours']/n:.3f} · hwp-cli {tot['cli']/n:.3f} | 쪽수일치 {cnt['ours']}/{n} · {cnt['cli']}/{n}")

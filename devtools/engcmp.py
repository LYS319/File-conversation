import json, pymupdf
from pathlib import Path
from PIL import Image, ImageOps
IN, OURS, CLI = Path('/in'), Path('/ours'), Path('/cli')
man = [m for m in json.loads((IN / 'manifest.json').read_text(encoding='utf-8')) if 'oracle_pdf' in m]
def grid(page):
    pm = page.get_pixmap(matrix=pymupdf.Matrix(0.6, 0.6), colorspace=pymupdf.csGRAY)
    im = ImageOps.invert(Image.frombytes('L', (pm.width, pm.height), pm.samples)).resize((40, 56), Image.BOX)
    return list(im.getdata())
def sim(a, b):
    num = sum(min(x, y) for x, y in zip(a, b)); den = sum(max(x, y) for x, y in zip(a, b))
    return num / den if den else 1.0
def score(ref, x):
    n = max(len(ref), len(x)); s = 0
    for i in range(n):
        s += sim(grid(ref[i]), grid(x[i])) if i < len(ref) and i < len(x) else 0
    return s / n
rows = []; tot = {'ours': 0, 'cli': 0}; cnt = {'ours': 0, 'cli': 0}
for i, m in enumerate(man):
    stem = Path(m['path']).stem
    ref = pymupdf.open(str(IN / m['oracle_pdf']))
    r = {'doc': m['path'][-34:], 'ref': len(ref)}
    for k, d in (('ours', OURS), ('cli', CLI)):
        f = d / f'{i:02d}_{stem}.pdf'
        x = pymupdf.open(str(f)); r[k] = len(x); r[k + '_s'] = score(ref, x)
        tot[k] += r[k + '_s']; cnt[k] += r[k] == len(ref)
    rows.append(r)
print('문서 | 한컴쪽 | 우리쪽 우리유사도 | cli쪽 cli유사도')
for r in rows: print(f"{r['doc']} | {r['ref']} | {r['ours']} {r['ours_s']:.2f} | {r['cli']} {r['cli_s']:.2f}")
n = len(rows)
print(f"평균 유사도 우리 {tot['ours']/n:.3f} cli {tot['cli']/n:.3f} | 쪽수일치 우리 {cnt['ours']}/{n} cli {cnt['cli']}/{n}")

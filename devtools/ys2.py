import json, pymupdf, sys
from pathlib import Path
IN = Path('/in'); OUT = Path('/out')
m = next(m for m in json.loads((IN / 'manifest.json').read_text(encoding='utf-8')) if m['path'].endswith(sys.argv[1]) and 'oracle_pdf' in m)
n = int(sys.argv[2])
for name, f in (('한컴', IN / m['oracle_pdf']), ('우리', OUT / 'cmp_now.pdf')):
    pg = pymupdf.open(str(f))[0]
    ls = []
    for b in pg.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            t = ''.join(s['text'] for s in l['spans']).strip()
            if t: ls.append((round(l['bbox'][1], 1), round(l['bbox'][0]), t[:12]))
    ls.sort(); print(name, ls[:n])

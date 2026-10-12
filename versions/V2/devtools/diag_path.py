import json, subprocess, sys, pymupdf
from pathlib import Path
IN, OUT = Path('/in'), Path('/out')
suffix = sys.argv[1]; marks = sys.argv[2:]
m = next(m for m in json.loads((IN / 'manifest.json').read_text(encoding='utf-8')) if m['path'].endswith(suffix) and 'oracle_pdf' in m)
pdf = OUT / 'diag_path_now.pdf'
subprocess.run([sys.executable, '/work/convert.py', str(IN / m['path']), str(pdf)], capture_output=True)
for name, doc in (('한컴', pymupdf.open(str(IN / m['oracle_pdf']))), ('우리', pymupdf.open(str(pdf)))):
    print('==', name, len(doc), '쪽')
    for pi in range(len(doc)):
        hits = []
        for k in marks:
            for r in doc[pi].search_for(k)[:2]: hits.append(f'{k}@{r.y0:.0f}')
        ys = [b[3] for b in doc[pi].get_text('blocks') if b[4].strip() and '- ' not in b[4][:3]]
        print(f' p{pi+1} 마지막글 y={max(ys) if ys else 0:.0f}', ' '.join(hits))

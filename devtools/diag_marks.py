import json, sys, pymupdf
from pathlib import Path
IN, OUT = Path('/in'), Path('/out')
stem = sys.argv[1]; marks = sys.argv[2:]
m = next(m for m in json.loads((IN / 'manifest.json').read_text(encoding='utf-8')) if Path(m['path']).stem == stem and 'oracle_pdf' in m)
for name, doc in (('한컴', pymupdf.open(str(IN / m['oracle_pdf']))), ('우리', pymupdf.open(str(OUT / f'{stem}_now.pdf')))):
    print('==', name, len(doc), '쪽')
    for pi in range(len(doc)):
        hits = []
        for k in marks:
            for r in doc[pi].search_for(k)[:2]: hits.append(f'{k}@{r.y0:.0f}')
        # 쪽의 가장 아래 글자 위치
        ys = [b[3] for b in doc[pi].get_text('blocks') if b[4].strip() and '- ' not in b[4][:3]]
        print(f' p{pi+1} 마지막글 y={max(ys) if ys else 0:.0f}', ' '.join(hits))

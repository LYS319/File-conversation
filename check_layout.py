"""레이아웃 점검: 한컴이 만든 정답 PDF 가 있는 문서를 PDF 로 바꿔, 쪽 수가 한컴과 얼마나 같은지 잰다.
    python check_layout.py 입력폴더(manifest.json 이 있는 곳) 출력폴더
필요: weasyprint(PDF 엔진), pymupdf(정답 PDF 쪽 수 읽기). 운영 이미지에는 pymupdf 가 없으므로 시험용 이미지(pdftest)에서 돌린다.
manifest.json 은 항목마다 {"path": 문서, "oracle_pdf": 정답 PDF} 를 가진다(corpus/rhwp/ 참고)."""
import json, os, subprocess, sys, time
from pathlib import Path
import pymupdf

HERE = Path(__file__).resolve().parent


def main(inp, outp):
    inp, outp = Path(inp), Path(outp); outp.mkdir(parents=True, exist_ok=True)
    man = [m for m in json.loads((inp / 'manifest.json').read_text(encoding='utf-8')) if 'oracle_pdf' in m]
    rows, same, gap = [], 0, 0
    for i, m in enumerate(man):
        src = inp / m['path']; pdf = outp / f'{i:02d}_{src.stem}.pdf'
        t = time.time()
        r = subprocess.run([sys.executable, str(HERE / 'convert.py'), str(src), str(pdf)], capture_output=True, text=True, encoding='utf-8',
                           env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
        ref = len(pymupdf.open(str(inp / m['oracle_pdf'])))
        if r.returncode: rows.append((m['path'], '실패', ref, '', r.stderr.strip().splitlines()[-1][:60])); continue
        ours = len(pymupdf.open(str(pdf)))
        same += ours == ref; gap += abs(ours - ref)
        rows.append((m['path'], ours, ref, f'{time.time() - t:.1f}s', 'OK' if ours == ref else f'{ours - ref:+d}쪽'))
    lines = ['문서 | 우리 | 한컴 | 시간 | 판정'] + [' | '.join(str(c) for c in r) for r in rows]
    lines.append(f'\n쪽 수 같음 {same}/{len(rows)} · 쪽 수 차이 합계 {gap}')
    (outp / 'layout_report.txt').write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    if len(sys.argv) != 3: sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])

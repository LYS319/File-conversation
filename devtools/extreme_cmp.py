"""극단값 문서를 세 엔진(우리 변환기 · hwp-cli · rhwp)으로 PDF 로 바꿔 용량·쪽 수·PDF 에 든 그림 수·걸린 시간을 비교한다.
    sh devtools/run_extreme_cmp.sh        (한 번에: 우리·rhwp 는 격리 컨테이너, hwp-cli 는 윈도 호스트 → corpus/_extreme_cmp/ → 표)
    python extreme_cmp.py run <ours|rhwp|cli> <극단값 폴더> <출력.jsonl> [결과 PDF 폴더]    (낱개 실행; ours·rhwp 는 컨테이너 안에서)
    python extreme_cmp.py table <극단값 폴더> <jsonl 폴더> [그림 폴더 링크]                      (마크다운 표를 출력; 링크를 주면 '비교 그림' 열)
    python extreme_cmp.py figs <극단값 폴더> <jsonl 폴더> <출력 폴더>                           (문서마다 한컴·우리·hwp-cli·rhwp·차이를 한 장 그림으로, 호스트에서)
그림 수 = 결과 PDF 에 든 서로 다른 이미지 개체(xref) 수. 시간 = 변환 명령 한 번의 벽시계(파이썬 시작·PDF 쓰기 포함). 모두 로컬 처리(외부 전송 없음)."""
import json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RHWP = ['/x/rhwp', 'export-pdf', '{src}', '-o', '{dst}', '--font-path', '/usr/share/fonts', '--fallback-serif', 'NanumMyeongjo',
        '--fallback-sans', 'NanumGothic', '--fallback-mono', 'NanumGothicCoding', '--compat', '2022']
TIMEOUT = 900


def norm(name): return re.sub(r'^(\d+_|가장긴_|가장짧은_|가장큰_|그림많은_)', '', name)


def docs(root):
    """극단값 폴더의 hwp·hwpx 를 이름(앞 번호 뗀)으로 합친다 -> [(이름, 경로, [분류 폴더…])]. 같은 파일이 여러 분류에 나오고, 큰 파일은 한 곳에만 있다."""
    seen = {}
    for p in sorted(Path(root).rglob('*')):
        if p.suffix.lower() in ('.hwp', '.hwpx') and p.is_file():
            e = seen.setdefault(norm(p.name), [p, []]); e[1].append(p.parent.name)
    return [(k, v[0], v[1]) for k, v in seen.items()]


def measure(pdf):
    import pymupdf
    d = pymupdf.open(str(pdf)); n = len(d); xs = set()
    for pg in d: xs.update(i[0] for i in pg.get_images(full=True))
    return n, len(xs)


def run(engine, root, out_jsonl, pdf_dir=None):
    tmp = Path(pdf_dir or tempfile.mkdtemp()); tmp.mkdir(parents=True, exist_ok=True)
    rows = []
    work = Path(tempfile.mkdtemp())
    for name, src0, cats in docs(root):
        src = work / ('in' + src0.suffix); shutil.copyfile(src0, src)      # 윈도 폴더 바인드 마운트로 큰 파일을 읽으면 느려 시간이 왜곡된다(함정.md) — 측정 전에 로컬로 복사
        dst = tmp / (Path(name).stem[:50] + '.pdf'); dst.unlink(missing_ok=True)
        if engine == 'ours': cmd = [sys.executable, str(HERE.parent / 'convert.py'), str(src), str(dst)]
        elif engine == 'rhwp': cmd = [c.format(src=src, dst=dst) for c in RHWP]
        else: cmd = [str(HERE.parents[0] / 'tools' / 'hwp-cli' / 'hwp.exe'), 'render', '--format', 'pdf', '-o', str(dst), str(src)]
        t = time.time(); err = ''
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
            if r.returncode: err = (r.stderr or r.stdout).decode('utf-8', 'replace').strip().splitlines()[-1:][0][:80] if (r.stderr or r.stdout) else 'exit %d' % r.returncode
        except subprocess.TimeoutExpired: err = '시간 초과 %ds' % TIMEOUT
        secs = round(time.time() - t, 1)
        row = dict(name=name, engine=engine, size=src0.stat().st_size, cats=cats, secs=secs, err=err, pages=None, images=None)
        if dst.exists() and dst.stat().st_size and not err:
            try: row['pages'], row['images'] = measure(dst)
            except Exception as e: row['err'] = type(e).__name__
        src.unlink(missing_ok=True); rows.append(row); print(engine, name[:50], row['pages'], row['images'], secs, err, flush=True)
        Path(out_jsonl).write_text('\n'.join(json.dumps(x, ensure_ascii=False) for x in rows), encoding='utf-8')


def hancom_pdfs():
    """한컴 정답 PDF: 공개 코퍼스 manifest 와 사용자 manifest 의 oracle_pdf 로(이름이 같은 것) -> {파일 이름: (PDF 경로, nup)}."""
    base = HERE.parents[0] / 'corpus'; out = {}
    for mf, pre in ((base / 'rhwp2' / 'manifest.json', base / 'rhwp2'), (base / 'rhwp' / 'manifest.json', base / 'rhwp'), (base / 'user_manifest.json', base)):
        if not mf.exists(): continue
        for m in json.loads(mf.read_text(encoding='utf-8')):
            pdf = pre / m['oracle_pdf'] if m.get('oracle_pdf') else None
            if pdf and pdf.exists(): out.setdefault(Path(m['path']).name, (pdf, m.get('nup', 1)))
    return out


def hancom_pages(root):
    """한컴 정답 PDF 쪽 수(모아찍기 nup 면 한 장에 nup 쪽)."""
    import pymupdf
    return {k: len(pymupdf.open(str(p))) * n for k, (p, n) in hancom_pdfs().items()}


def table(root, jdir, figdir=None):
    R = {e: {json.loads(l)['name']: json.loads(l) for l in (Path(jdir) / (e + '.jsonl')).read_text(encoding='utf-8').splitlines() if l} for e in ('ours', 'cli', 'rhwp') if (Path(jdir) / (e + '.jsonl')).exists()}
    hp = hancom_pages(root); f = lambda r: ('실패:' + r['err'][:18]) if r and r['err'] else ('—' if not r else '%s쪽·%s장·%.1fs' % (r['pages'], r['images'], r['secs']))
    print('| 문서 | 극단 분류 | 용량 | 한컴 쪽 | 우리 | hwp-cli | rhwp |\n|---|---|---|---|---|---|---|')
    ok = {e: [0, 0, 0.0] for e in R}      # 쪽 수 일치 건수, 비교 가능 건수, 걸린 시간 합
    for i, (name, src, cats) in enumerate(docs(root)):
        for e in R:
            r = R[e].get(name)
            if r and not r['err']: ok[e][2] += r['secs']
            if r and not r['err'] and name in hp: ok[e][1] += 1; ok[e][0] += r['pages'] == hp[name]
        sz = src.stat().st_size; szs = '%.1fMB' % (sz / 1e6) if sz >= 1e6 else '%dKB' % (sz // 1000)
        fig = ' [그림](%s/%s) |' % (figdir, fig_name(i, name).replace(' ', '%20')) if figdir else ''
        print('| `%s` | %s | %s | %s | %s | %s | %s |%s' % (name[:46], ', '.join(c.split('.')[0] + c.split('.', 1)[1][:6] for c in cats), szs, hp.get(name, '—'), f(R.get('ours', {}).get(name)), f(R.get('cli', {}).get(name)), f(R.get('rhwp', {}).get(name)), fig))
    nm = {'ours': '우리', 'cli': 'hwp-cli', 'rhwp': 'rhwp'}
    print('\n한컴과 쪽 수 같음: ' + ' · '.join('%s %d/%d' % (nm[e], ok[e][0], ok[e][1]) for e in ok) + '  /  걸린 시간 합(성공한 것): ' + ' · '.join('%s %.0f초' % (nm[e], ok[e][2]) for e in ok))


def fig_name(i, name): return '%02d_%s.png' % (i + 1, re.sub(r'[()]', '', Path(name).stem[:40]))      # 괄호는 마크다운 링크를 깨므로 뺀다


def ptext(doc, i, nup=1):
    """쪽 i(0부터)의 글(공백 뺌). 모아찍기면 반쪽만. 없는 쪽이면 None."""
    import pymupdf, re
    if i // nup >= len(doc): return None
    pg = doc[i // nup]; w = pg.rect.width / nup
    return re.sub(r'\s+', '', pg.get_text(clip=pymupdf.Rect(w * (i % nup), 0, w * (i % nup + 1), pg.rect.height)))


def first_diff(ref, others):
    """한컴 쪽과 첫머리 글이 처음 달라지는 쪽(0부터). others 순서대로 먼저 갈라지는 엔진을 따라 간다: 우리가 끝까지 같으면 다음 엔진, 다 같으면 0."""
    from difflib import SequenceMatcher
    for o in others:
        if o[0] is None: continue
        for i in range(max(len(ref[0]) * ref[1], len(o[0]))):
            a, b = ptext(ref[0], i, ref[1]), ptext(o[0], i)
            if a is None or b is None or SequenceMatcher(None, a[:300], b[:300]).ratio() < .9: return i
    return 0


def compose(title, cols, pg, H=900, crop=None, diff_col=True, sub_size=18, label_size=34):
    """cols = [(제목, 부제, pymupdf 문서 또는 None, nup[, 제목 색 (r,g,b)])] 의 쪽 pg(0부터)를 한 장 그림(PIL)으로. 첫 열이 한컴 정답이면 한컴 대 둘째 열의 차이 열을 붙인다.
    crop = (x0, y0, x1, y1) 쪽 비율(0~1)이면 그 부분만 확대해 보인다(PPT 용)."""
    import pymupdf
    from PIL import Image, ImageDraw, ImageFont
    sys.path.insert(0, str(HERE)); from side_by_side import diff
    F = lambda sz, b=False: ImageFont.truetype('C:/Windows/Fonts/malgun%s.ttf' % ('bd' if b else ''), sz)

    def panel(doc, i, nup):
        if doc is None or i // nup >= len(doc): return None
        pgx = doc[i // nup]; w = pgx.rect.width / nup; r = pymupdf.Rect(w * (i % nup), 0, w * (i % nup + 1), pgx.rect.height)
        if crop: r = pymupdf.Rect(r.x0 + r.width * crop[0], r.y0 + r.height * crop[1], r.x0 + r.width * crop[2], r.y0 + r.height * crop[3])
        z = H / r.height; pm = pgx.get_pixmap(matrix=pymupdf.Matrix(z, z), clip=r)
        return Image.frombytes('RGB', (pm.width, pm.height), pm.samples)

    imgs = [(c, panel(c[2], pg, c[3])) for c in cols]
    if diff_col and cols[0][0].startswith('0.') and imgs[0][1] and imgs[1][1]: imgs.append((('D. 차이', '빨강=한컴에만 · 파랑=우리에만', None, 1), diff(imgs[0][1].convert('L'), imgs[1][1].convert('L'))))
    gap = 40; W = sum((im.width if im else 300) for _, im in imgs) + gap * (len(imgs) + 1); top = 170 if title else 120
    cv = Image.new('RGB', (W, H + top + 20), 'white'); d = ImageDraw.Draw(cv); x = gap
    if title: d.text((gap, 14), title, font=F(32, True), fill=(20, 20, 20))
    for c, im in imgs:
        t, sub, doc, nup = c[:4]; tot = '' if doc is None else ' · 전체 %d쪽' % (len(doc) * nup)
        d.text((x, top - 100), t, font=F(label_size, True), fill=c[4] if len(c) > 4 else (200, 20, 20)); d.text((x, top - 100 + label_size + 14), (sub + tot).strip(' ·'), font=F(sub_size), fill=(90, 90, 90))
        if im: cv.paste(im, (x, top)); d.rectangle((x - 1, top - 1, x + im.width, top + im.height), outline=(150, 150, 150)); x += im.width + gap
        else: d.text((x, top), '(이 쪽 없음)' if doc else '(결과 없음)', font=F(24), fill=(150, 150, 150)); x += 300 + gap
    return cv


def figs(root, jdir, outdir):
    """문서마다 한컴 · 우리 · hwp-cli · rhwp · 차이(한컴 대 우리)를 한 장 그림으로 — 한컴과 첫머리 글이 처음 갈라지는 쪽(없으면 1쪽). outdir/NN_이름.png + index.md"""
    import pymupdf
    hp = hancom_pdfs(); outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    ENG = [('ours', '우리 변환기', 'HTML → WeasyPrint · 나눔 글꼴'), ('cli', 'hwp-cli', 'hwp.exe render · 윈도 글꼴'), ('rhwp', 'rhwp', 'export-pdf · 나눔 글꼴')]
    md = ['# 극단값 엔진 비교 그림 (한컴 · 우리 · hwp-cli · rhwp · 차이)\n', '문서마다 **한컴 정답과 첫머리 글이 처음 갈라지는 쪽**(우리 기준, 우리가 끝까지 같으면 다른 엔진 기준, 다 같으면 1쪽)을 나란히 놓았다. 차이 그림: 빨강=한컴에만, 파랑=우리에만, 검정=둘 다. 한컴 정답이 없는 문서는 그 열이 빠진다. 다시 만들기: `python devtools/extreme_cmp.py figs 테스트파일/04.극단값 corpus/_extreme_cmp <출력 폴더>`.\n']
    for n, (name, src, cats) in enumerate(docs(root)):
        stem = Path(name).stem[:50]; cols = []
        if name in hp: cols.append(('0. 한컴 정답', 'Hancom PDF', pymupdf.open(str(hp[name][0])), hp[name][1]))
        for k, (e, t, sub) in enumerate(ENG):
            f = Path(jdir) / ('pdf_' + e) / (stem + '.pdf')
            cols.append((chr(65 + k) + '. ' + t, sub, pymupdf.open(str(f)) if f.exists() and f.stat().st_size else None, 1))
        ref = cols[0] if name in hp else None
        pg = first_diff((ref[2], ref[3]), [(c[2], 1) for c in cols[1:]]) if ref else 0
        r0 = next(c for c in cols if c[2])[2][0].rect; H = int(min(900, 700 * r0.height / r0.width))      # 가로 용지는 낮게(열 폭 700 안팎)
        cv = compose('%s — %d쪽 (%s)' % (name[:60], pg + 1, '한컴과 처음 갈라지는 쪽' if ref and pg else '첫 쪽'), cols, pg, H)
        fn = fig_name(n, name); cv.save(outdir / fn, optimize=True)
        md.append('## %s\n- %s쪽 · %s\n\n![%s](%s)\n' % (name, pg + 1, ' / '.join('%s %s쪽' % (c[0][3:], len(c[2]) * c[3]) for c in cols if c[2]), name, fn.replace(' ', '%20')))
        print('그림', fn, flush=True)
    (outdir / 'index.md').write_text('\n'.join(md), encoding='utf-8')


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[0] == 'run': run(a[1], a[2], a[3], a[4] if len(a) > 4 else None)
    elif a[0] == 'table': table(a[1], a[2], a[3] if len(a) > 3 else None)
    elif a[0] == 'figs': figs(a[1], a[2], a[3])

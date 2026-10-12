"""로컬 정확도 점검(토큰 0, 문서가 밖으로 안 나감): 문서를 우리 변환기로 PDF 로 바꿔 한컴 정답 PDF 와 숫자로 비교한다.
    python eval_layout.py <기준폴더> <manifest.json> <출력폴더> [--workers 3] [--only 부분문자열] [--reuse]
기준폴더: manifest 의 path·oracle_pdf 가 상대 경로면 여기서 찾는다(절대 경로면 그대로).
지표(문서마다): 쪽 수 / 글 재현율·정밀도(공백 뺀 글자 다중집합) / 쪽 시작 일치(정답 각 쪽의 첫 글자들이 우리 같은 쪽 머리에 있는가)
               / 글 위치 오차(같은 쪽에서 한 번만 나오는 낱말의 가로·세로 어긋남 중앙값, pt) / 잉크 격자 유사도(15pt 칸).
split: 경로 해시로 dev(75%)/holdout(25%) 를 나눈다. 결함을 찾을 땐 dev 만 자세히 보고, holdout 은 집계만 본다(과적합 방지).
필요: pymupdf, pillow, weasyprint(변환기). 시험용 이미지 pdftest:wp 에서 격리 실행한다(run_eval.sh)."""
import argparse, collections, hashlib, json, os, re, statistics, subprocess, sys, time, unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pymupdf
from PIL import Image, ImageOps

HERE = Path(__file__).resolve().parent
CONVERT = HERE.parent / 'convert.py' if (HERE.parent / 'convert.py').exists() else HERE / 'convert.py'
MAX_PAGES = 40  # 위치·유사도는 앞 40쪽만(긴 문서 시간)


def doc_key(path):
    """같은 문서의 다른 형식·버전(hwp/hwpx 쌍, -hancom·-2020 꼬리, re-font 가족)은 한 묶음 — 묶음 단위로 dev/holdout 을 나눈다. 쪽 단위로 무작위 분할하면
    같은 문서가 양쪽에 걸려 점수가 부풀려진다(DocLayNet 논문 5장: 쪽 단위 분할이 문서 단위보다 약 10%p 높게 나옴)."""
    s = re.sub(r'(-(hwpx?|hancom|20\d\d))+$', '', os.path.basename(path).rsplit('.', 1)[0].lower())
    return 're-font' if s.startswith('re-font') else s


def split_of(path):
    return 'holdout' if int(hashlib.sha1(doc_key(path).encode('utf-8')).hexdigest()[:2], 16) % 4 == 0 else 'dev'


def norm(s):
    return ''.join(unicodedata.normalize('NFKC', s).split())


def page_words(page):
    return [(norm(w[4]), w[0], w[1]) for w in page.get_text('words') if norm(w[4])]


def grid(page):
    pm = page.get_pixmap(matrix=pymupdf.Matrix(0.6, 0.6), colorspace=pymupdf.csGRAY)
    im = ImageOps.invert(Image.frombytes('L', (pm.width, pm.height), pm.samples)).resize((40, 56), Image.BOX)
    return list(im.get_flattened_data() if hasattr(im, 'get_flattened_data') else im.getdata())


def sim(a, b):
    num = sum(min(x, y) for x, y in zip(a, b)); den = sum(max(x, y) for x, y in zip(a, b))
    return num / den if den else 1.0


class Pages:
    """PDF 한 권을 '문서 쪽' 목록으로 본다. nup=2 이면 한 장에 두 쪽을 모아 찍은 PDF(가로 용지, 0.707배)를 왼쪽·오른쪽 절반씩 한 쪽으로 푼다.
    뒤쪽의 빈 쪽(모아찍기 마지막 장의 빈 절반)은 뺀다."""
    def __init__(self, doc, nup=1):
        self.doc, self.nup = doc, nup
        self.n = len(doc) * nup
        while nup > 1 and self.n > 1 and not self.words(self.n - 1): self.n -= 1

    def __len__(self): return self.n

    def _half(self, i):
        pg = self.doc[i // self.nup]; w = pg.rect.width / self.nup
        return pg, pymupdf.Rect(w * (i % self.nup), 0, w * (i % self.nup + 1), pg.rect.height)

    def words(self, i):
        if self.nup == 1: return page_words(self.doc[i])
        pg, r = self._half(i); k = 1 / 0.7071   # 쪽 폭 595 -> 절반 421
        return [(norm(w[4]), (w[0] - r.x0) * k, w[1] * k) for w in pg.get_text('words', clip=r) if norm(w[4])]

    def text(self, i):
        if self.nup == 1: return norm(self.doc[i].get_text())
        return ''.join(w[0] for w in sorted(self.words(i), key=lambda t: (round(t[2] / 4), t[1])))

    def vlines(self, i):
        """쪽 안 세로선(표 칸 경계)의 x 좌표(pt, 문서 쪽 기준). 표 위치·칸 폭이 맞는지 보는 데 쓴다."""
        pg, r = (self.doc[i], None) if self.nup == 1 else self._half(i); k = 1 if self.nup == 1 else 1 / 0.7071
        x0 = r.x0 if r else 0.0; w = (r.x1 - r.x0) if r else pg.rect.width
        return sorted({round((d['rect'].x0 - x0) * k, 1) for d in pg.get_drawings() if d['rect'].width < 2.5 and d['rect'].height > 12 and x0 <= d['rect'].x0 < x0 + w})

    def grid(self, i):
        if self.nup == 1: return grid(self.doc[i])
        pg, r = self._half(i); s = 0.6 / 0.7071
        pm = pg.get_pixmap(matrix=pymupdf.Matrix(s, s), clip=r, colorspace=pymupdf.csGRAY)
        return list(ImageOps.invert(Image.frombytes('L', (pm.width, pm.height), pm.samples)).resize((40, 56), Image.BOX).getdata())


class Plain(Pages):
    def __init__(self, doc): super().__init__(doc, 1)


def metrics(ref, our):
    n_ref, n_our = len(ref), len(our)
    rt = [ref.text(i) for i in range(n_ref)]; ot = [our.text(i) for i in range(n_our)]
    cr, co = collections.Counter(''.join(rt)), collections.Counter(''.join(ot))
    inter = sum((cr & co).values())
    recall = inter / sum(cr.values()) if cr else 1.0
    prec = inter / sum(co.values()) if co else 1.0
    # 쪽 시작 일치: 정답 i쪽 첫 8글자 == 우리 i쪽 첫 8글자 (글이 없는 쪽은 둘 다 없을 때만)
    start = sum(1 for i in range(n_ref) if i < n_our and rt[i][:8] == ot[i][:8])
    # 글 위치: 같은 쪽에서 양쪽 모두 한 번만 나오는 낱말
    dxs, dys, sdxs, sdys = [], [], [], []
    for i in range(min(n_ref, n_our, MAX_PAGES)):
        a, b = collections.defaultdict(list), collections.defaultdict(list)
        for w, x, y in ref.words(i): a[w].append((x, y))
        for w, x, y in our.words(i): b[w].append((x, y))
        for w, v in a.items():
            if len(v) == 1 and len(b.get(w, ())) == 1:
                sdxs.append(b[w][0][0] - v[0][0]); sdys.append(b[w][0][1] - v[0][1]); dxs.append(abs(sdxs[-1])); dys.append(abs(sdys[-1]))
    hit = tot = 0
    for i in range(min(n_ref, n_our, 5)):
        a, b = ref.vlines(i), our.vlines(i)
        tot += len(a); hit += sum(1 for x in a if any(abs(x - y) <= 1.5 for y in b))
    inkn = min(max(n_ref, n_our), MAX_PAGES); ink = 0.0
    for i in range(inkn):
        ink += sim(ref.grid(i), our.grid(i)) if i < n_ref and i < n_our else 0
    med = lambda v: round(statistics.median(v), 1) if v else None
    p90 = lambda v: round(sorted(v)[int(len(v) * 0.9)], 1) if v else None
    return dict(ref=n_ref, ours=n_our, recall=round(recall, 3), prec=round(prec, 3), start=round(start / n_ref, 3) if n_ref else 1.0,
                dx=med(dxs), dy=med(dys), dy90=p90(dys), sdx=med(sdxs), sdy=med(sdys), anchors=len(dys), vl=round(hit / tot, 3) if tot else None, vln=tot, ink=round(ink / inkn, 3) if inkn else 1.0)


RHWP = ['/x/rhwp', 'export-pdf', '{src}', '-o', '{dst}', '--font-path', '/usr/share/fonts', '--fallback-serif', 'NanumMyeongjo',
        '--fallback-sans', 'NanumGothic', '--fallback-mono', 'NanumGothicCoding', '--compat', '{compat}']     # 비교용 엔진(tools/rhwp, 격리 컨테이너 /x). 글꼴 이름이 안 맞으면 글자가 빈칸으로 나온다


def convert_one(args):
    i, src, dst, reuse, engine, compat = args
    if reuse and dst.exists(): return i, 0, 0.0, ''
    t = time.time()
    cmd = [sys.executable, str(CONVERT), str(src), str(dst)] if engine == 'ours' else [c.format(src=src, dst=dst, compat=compat) for c in RHWP]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                           errors='replace', timeout=400, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
        err = (r.stderr.strip().splitlines() or [''])[-1][:90] if r.returncode else ''
        return i, r.returncode, time.time() - t, err
    except subprocess.TimeoutExpired:
        return i, 124, time.time() - t, '시간 초과'


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('base'); ap.add_argument('manifest'); ap.add_argument('out')
    ap.add_argument('--workers', type=int, default=3); ap.add_argument('--only', default=''); ap.add_argument('--reuse', action='store_true')
    ap.add_argument('--engine', default='ours', choices=('ours', 'rhwp')); ap.add_argument('--compat', default='2022', help='rhwp 의 한글 조판 세대(2022|2024)')
    a = ap.parse_args()
    base, out = Path(a.base), Path(a.out); out.mkdir(parents=True, exist_ok=True)
    man = [m for m in json.loads(Path(a.manifest).read_text(encoding='utf-8')) if 'oracle_pdf' in m and a.only in m['path']]
    jobs = []
    for i, m in enumerate(man):
        src = base / m['path'] if not m['path'].startswith('/') else Path(m['path'])
        jobs.append((i, src, out / f'{i:03d}_{Path(m["path"]).stem[:40]}.pdf', a.reuse, a.engine, a.compat))
    with ThreadPoolExecutor(a.workers) as ex: conv = {r[0]: r for r in ex.map(convert_one, jobs)}
    rows = []
    for i, m in enumerate(man):
        row = dict(doc=m['path'], split=split_of(m['path']))
        _, rc, secs, err = conv[i]
        if rc: row.update(fail=err or f'rc={rc}'); rows.append(row); continue
        try:
            ref = pymupdf.open(str(base / m['oracle_pdf']))
            row.update(metrics(Pages(ref, m.get('nup', 1)), Plain(pymupdf.open(str(jobs[i][2]))))); row['sec'] = round(secs, 1)
            row['suspect'] = row['prec'] < 0.35      # 우리 글이 정답 PDF 의 3배 넘음 = 정답이 일부 쪽만 담았거나 빈 쪽(form-01, BookReview, memo_field). 집계에서 뺀다
        except Exception as e:
            row.update(fail=f'측정 실패 {type(e).__name__}: {e}'[:90])
        rows.append(row)
    (out / 'eval.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    lines = ['문서 | 분할 | 쪽(우리/한컴) | 글재현 | 글정밀 | 쪽시작 | dx | dy | dy90 | 부호dx | 부호dy | 세로선 | 유사도']
    for r in rows:
        if 'fail' in r: lines.append(f"{r['doc']} | {r['split']} | 실패: {r['fail']}"); continue
        lines.append(f"{r['doc']} | {r['split']} | {r['ours']}/{r['ref']}{'' if r['ours'] == r['ref'] else ' ✗'}{' ?정답의심' if r.get('suspect') else ''} | {r['recall']} | {r['prec']} | {r['start']} | {r['dx']} | {r['dy']} | {r['dy90']} | {r['sdx']} | {r['sdy']} | {r.get('vl')} | {r['ink']}")
    ok = [r for r in rows if 'fail' not in r and not r.get('suspect')]
    sus = [r for r in rows if r.get('suspect')]
    def agg(rs, tag):
        if not rs: return f'{tag}: 없음'
        same = sum(r['ours'] == r['ref'] for r in rs); gap = sum(abs(r['ours'] - r['ref']) for r in rs)
        m = lambda k: round(statistics.mean(r[k] for r in rs), 3)
        dy = [r['dy'] for r in rs if r['dy'] is not None]
        vls = [r for r in rs if r.get('vl') is not None]; vtxt = f'세로선 일치 {round(sum(r["vl"] * r["vln"] for r in vls) / max(1, sum(r["vln"] for r in vls)), 3)}({sum(r["vln"] for r in vls)}개) · ' if vls else ''
        return (f'{tag}: {len(rs)}건 · 쪽 수 같음 {same} · 차이 합계 {gap} · 글재현 {m("recall")} · 글정밀 {m("prec")} · 쪽시작 {m("start")} · '
                f'dy 중앙값의 평균 {round(statistics.mean(dy), 1) if dy else None} · {vtxt}유사도 {m("ink")}')
    env = sorted({(m.get('oracle_env') or {}).get('producer') or (f"한컴 {m['hancom']}" if m.get('hancom') else '출처 미기록') for m in man})
    lines += ['', '※ 정답지(한컴 PDF)는 한컴 버전·OS·글꼴·출력 경로에 따라 쪽 나눔이 달라질 수 있어 절대 정답이 아니라 비교 기준이다. 정답지 출처: ' + ', '.join(env)]
    lines += ['', agg(ok, '전체'), agg([r for r in ok if r['split'] == 'dev'], 'dev'), agg([r for r in ok if r['split'] == 'holdout'], 'holdout'),
              f"정답 의심(집계 제외) {len(sus)}건: " + ', '.join(r['doc'][-30:] for r in sus),
              f"실패 {sum('fail' in r for r in rows)}건: " + ', '.join(r['doc'][-30:] for r in rows if 'fail' in r)]
    (out / 'eval.txt').write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines[-4:]))


if __name__ == '__main__':
    main()

"""일반화 점검: 폴더 안의 HWP·HWPX 를 모두 변환해 보고, 샘플 3건 밖에서 깨지는 곳(오류·사설 문자·전각/반각 형태·구조 불일치)을 표로 낸다.
    python check_corpus.py 입력폴더 출력폴더        (출력: corpus_report.json, corpus_report.md)
변환은 앱과 같은 방식(별도 프로세스, 시간 제한)으로 돌린다. 모르는 문서를 읽는 일이므로 격리된 컨테이너(--network none, 읽기 전용)에서 돌리는 것을 권한다."""
import difflib, json, os, re, subprocess, sys, tempfile, time, zipfile
from collections import Counter
from pathlib import Path
import lxml.html
from lxml import etree
import convert, hwp2html

HERE = Path(__file__).resolve().parent
HP = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'
norm = lambda t: re.sub(r'\s+', '', t)
PUA_RE = convert.PUA_RE
FF_RE = re.compile('[＀-￯]')                                     # 전각·반각 형태 블록(｢ ｣ ｡ ﾟ …)
JAMO_RE = re.compile('[ᄀ-ᇿꥠ-꥿ힰ-퟿]')           # 옛한글(조합형 자모)만. ㅇ·ㆍ 같은 호환 자모(3130~318F)는 목록 기호로 흔히 쓰는 정상 글자라 뺀다
HANDLED_RUN = {'t', 'tbl', 'pic', 'secPr', 'ctrl', 'checkBtn', 'radioBtn', 'btn', 'rect'}      # hwpx2html 이 처리하는 run 안의 요소


def run_convert(src, dst, timeout=180):
    t = time.time()
    try:
        r = subprocess.run([sys.executable, str(HERE / 'convert.py'), str(src), str(dst)], capture_output=True, text=True, encoding='utf-8',
                           timeout=timeout, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    except subprocess.TimeoutExpired:
        return False, round(time.time() - t, 1), f'시간 초과({timeout}초)'
    err = next((l for l in reversed(r.stderr.splitlines()) if l.strip()), '')
    return r.returncode == 0, round(time.time() - t, 1), ('' if r.returncode == 0 else err[:160])


def hwpx_facts(path):
    """HWPX 원본의 글자·표·그림·문단 수와 줄 나눔(linesegarray) 수."""
    z = zipfile.ZipFile(path)
    text, hf_text, tbl, pic, par, lsa, unsup = '', '', 0, 0, 0, 0, Counter()
    for n in sorted(n for n in z.namelist() if re.match(r'Contents/section\d+\.xml', n)):
        root = etree.fromstring(z.read(n))
        in_hf = {d for hf in root.iter(HP + 'header', HP + 'footer') for d in hf.iter()}      # 머리글·바닥글은 본문 앞/끝으로 옮겨지므로 따로 센다
        for el in root.iter():            # 문서 순서대로: 글(hp:t)과, 변환기가 기호+설명으로 바꾸는 양식 컨트롤을 같이 센다
            tag = etree.QName(el).localname if isinstance(el.tag, str) else ''
            add = ''
            if tag == 't': add = ''.join(el.itertext())
            elif tag in ('checkBtn', 'radioBtn', 'btn'):
                mark = {'checkBtn': ('☐', '☑'), 'radioBtn': ('○', '◉')}.get(tag)
                add = (mark[el.get('value') == 'CHECKED'] if mark else '') + (el.get('caption') or '')
            if el in in_hf: hf_text += add
            else: text += add
        tbl += sum(1 for _ in root.iter(HP + 'tbl')); pic += sum(1 for _ in root.iter(HP + 'pic'))
        par += sum(1 for _ in root.iter(HP + 'p')); lsa += sum(1 for _ in root.iter(HP + 'lineseg'))
        for run in root.iter(HP + 'run'):
            for ch in run:
                tag = etree.QName(ch).localname
                if tag not in HANDLED_RUN: unsup[tag] += 1          # 변환기가 조용히 건너뛰는 요소
    return dict(text=norm(text), hf=norm(hf_text), tbl=tbl, pic=pic, par=par, lineseg=lsa, unsup=dict(unsup))


def html_facts(path):
    h = Path(path).read_text(encoding='utf-8')
    doc = lxml.html.document_fromstring(h)
    tbl, img = len(doc.xpath('//table')), len(doc.xpath('//img'))          # 머리글을 떼기 전에 센다(그 안의 표도 포함)
    hf = ''
    for d in doc.xpath('//div[@class="hwp-header" or @class="hwp-footer"]'): hf += d.text_content(); d.drop_tree()
    text = norm(doc.body.text_content())
    return dict(text=text, hf=norm(hf), tbl=tbl, img=img,
                pua=sorted({ord(c) for c in PUA_RE.findall(text)}), ff=sorted({ord(c) for c in FF_RE.findall(text)}),
                jamo=len(JAMO_RE.findall(text)))


def kept(a, b):
    """원본 글자 a 가 변환 결과 b 에 얼마나 남았나(0~1). 결과에 글자가 더 들어간 것(자동 번호 등)은 손해로 치지 않는다."""
    if a == b or not a: return 1.0
    sm = difflib.SequenceMatcher(None, a, b, autojunk=len(a) + len(b) > 60000)      # 큰 문서는 autojunk 로 속도를 얻는 대신 근사값
    return round(sum(m.size for m in sm.get_matching_blocks()) / len(a), 4)


def check(src, tmp):
    row = dict(file=str(src.relative_to(ROOT_IN)).replace(os.sep, '/'), bytes=src.stat().st_size)
    try: kind, why = convert.inspect(src)
    except ValueError as e: return {**row, 'kind': '?', 'error': f'판별 실패: {e}'}
    row['kind'] = kind
    out_html = tmp / 'o.html'
    ok, sec, err = run_convert(src, out_html)
    row.update(html_ok=ok, html_sec=sec)
    if not ok: return {**row, 'error': err}
    h = html_facts(out_html)
    row.update(html_tbl=h['tbl'], html_img=h['img'], pua=[f'U+{c:X}' for c in h['pua']], ff=[f'U+{c:X}' for c in h['ff']], jamo=h['jamo'])
    if kind == 'hwpx':
        s = hwpx_facts(src)
        row.update(src_tbl=s['tbl'], src_pic=s['pic'], src_par=s['par'], lineseg=s['lineseg'], unsup=s['unsup'],
                   text_ratio=kept(s['text'].translate(hwp2html.PUA), h['text']),
                   hf_ratio=kept(s['hf'].translate(hwp2html.PUA), h['hf']) if s['hf'] else None)
    else:                                              # HWP: 원본 글자를 직접 못 읽으니 HWP→HWPX 결과와 HTML 을 서로 견준다
        out_x = tmp / 'o.hwpx'
        ok2, sec2, err2 = run_convert(src, out_x)
        row.update(hwpx_ok=ok2, hwpx_sec=sec2)
        if ok2:
            s = hwpx_facts(out_x); row.update(src_tbl=s['tbl'], src_pic=s['pic'], text_ratio=kept(s['text'], h['text']))
        else: row['error'] = err2
    return row


def verdict(r):
    """한 줄 판정: 문제가 있는 것만 이유를 모아서."""
    if r.get('error'): return '❌ ' + r['error']
    why = []
    if r.get('pua'): why.append('사설 문자 ' + ' '.join(r['pua'][:6]))
    if r.get('jamo'): why.append(f'옛한글 {r["jamo"]}자(글꼴 지원 필요)')
    if r.get('text_ratio', 1) < 0.999: why.append(f'글자 보존 {r["text_ratio"]:.1%}')
    if (r.get('hf_ratio') or 1) < 0.999: why.append(f'머리글·바닥글 보존 {r["hf_ratio"]:.1%}')
    if 'src_tbl' in r and r['src_tbl'] != r['html_tbl']: why.append(f'표 {r["src_tbl"]}→{r["html_tbl"]}')
    pic = r.get('src_pic')
    if pic is not None and pic != r['html_img']: why.append(f'그림 {pic}→{r["html_img"]}')
    if r.get('unsup'): why.append('건너뛴 요소 ' + ' '.join(f'{k}×{v}' for k, v in r['unsup'].items()))
    if r.get('hwpx_ok') is False: why.append('HWP→HWPX 실패')
    return ('⚠️ ' + ' · '.join(why)) if why else '✅'


def main(inp, outp):
    global ROOT_IN
    ROOT_IN = Path(inp); outp = Path(outp); outp.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in ROOT_IN.rglob('*') if p.is_file() and p.suffix.lower() in ('.hwp', '.hwpx'))
    rows = []
    for p in files:
        with tempfile.TemporaryDirectory() as d:
            r = check(p, Path(d)); r['verdict'] = verdict(r); rows.append(r)
        print(f'{r["verdict"][:70]:70}  {r["file"]}', flush=True)
    (outp / 'corpus_report.json').write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding='utf-8')
    ok = sum(r['verdict'] == '✅' for r in rows); bad = sum(r['verdict'].startswith('❌') for r in rows)
    md = [f'# 일반화 점검 보고 — {len(rows)}건', '', f'- ✅ 이상 없음 **{ok}** · ⚠️ 주의 **{len(rows) - ok - bad}** · ❌ 실패 **{bad}**', '',
          '| 판정 | 형식 | 파일 | 초 | 표(원본→HTML) | 그림 | 전각·반각 형태 |', '|---|---|---|---:|---|---|---|']
    for r in rows:
        md.append(f'| {r["verdict"]} | {r.get("kind")} | {r["file"]} | {r.get("html_sec", "")} | {r.get("src_tbl", "")}→{r.get("html_tbl", "")} | '
                  f'{r.get("src_pic", "")}→{r.get("html_img", "")} | {" ".join(r.get("ff", [])[:6])} |')
    pua = Counter(c for r in rows for c in r.get('pua', [])); ff = Counter(c for r in rows for c in r.get('ff', []))
    md += ['', '## 남은 사설 영역 문자(브라우저에서 □ 로 보일 수 있음)', ', '.join(f'{c}×{n}문서' for c, n in pua.most_common()) or '(없음)',
           '', '## 전각·반각 형태 문자(글꼴에 따라 폭이 달라질 수 있음)', ', '.join(f'{c}×{n}문서' for c, n in ff.most_common()) or '(없음)']
    (outp / 'corpus_report.md').write_text('\n'.join(md), encoding='utf-8')
    print(f'\n✅ {ok} · ⚠️ {len(rows) - ok - bad} · ❌ {bad}  (보고서: {outp})')


if __name__ == '__main__':
    if len(sys.argv) != 3: sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])

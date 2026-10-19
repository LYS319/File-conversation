"""HWPX<->HTML 변환기 회귀 점검 (API 호출 없음). python test_hwpx_roundtrip.py"""
import difflib, re, tempfile, zipfile
from pathlib import Path
import lxml.html
from lxml import etree
import hwp2html, hwpx2html, html2hwpx

HP = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'
HH = '{http://www.hancom.co.kr/hwpml/2011/head}'
HERE = Path(__file__).resolve().parent
DATA = HERE          # samples/ · results/ 가 있는 프로젝트 루트
norm = lambda t: re.sub(r'\s+', '', t)


def parts(hwpx):
    z = zipfile.ZipFile(hwpx)
    return etree.fromstring(z.read('Contents/section0.xml')), etree.fromstring(z.read('Contents/header.xml'))


def stats(hwpx):
    sec, _ = parts(hwpx)
    text = norm(''.join(t.xpath('string(.)') for t in sec.iter(HP + 't')))
    return dict(p=len(list(sec.iter(HP + 'p'))), tbl=len(list(sec.iter(HP + 'tbl'))), tc=len(list(sec.iter(HP + 'tc')))), text


def demo():
    tmp = Path(tempfile.mkdtemp())
    src = next((DATA / 'samples').glob('*.hwpx'), None)
    if src:  # 공고문 왕복: 문단·표·셀 수가 같아야 한다
        hwpx2html.convert(str(src), str(tmp / 'a.html'))
        html2hwpx.build(str(tmp / 'a.html'), str(tmp / 'a.hwpx'))
        (s0, t0), (s1, t1) = stats(src), stats(tmp / 'a.hwpx')
        assert s0 == dict(p=773, tbl=42, tc=472) and s1 == dict(p=770, tbl=42, tc=472), (s0, s1)    # 쪽 나누기 앞·문서 끝의 빈 문단 3개는 빈 쪽이 생기지 않게 HTML 에서 뺀다(hwpx2html.convert)
        r = difflib.SequenceMatcher(None, t0.translate(hwp2html.PUA), t1, autojunk=False).ratio()   # 사설 영역 문자는 진짜 기호로 바뀌는 게 정상이라 원본에도 같은 표를 적용
        assert r >= 0.9998, r  # 자동번호 문단 1곳이 글자 '1.'로 바뀌는 것만 허용
        print('공고문 왕복 OK', s1, round(r, 5))

    html = next((DATA / 'results/V2_채팅에서_만든_HTML').glob('*회의록*.html'), None)
    if html:  # 외부에서 만든 HTML(% 너비, <style> 클래스 규칙)
        html2hwpx.build(str(html), str(tmp / 'b.hwpx'))
        sec, head = parts(tmp / 'b.hwpx')
        s, t = stats(tmp / 'b.hwpx')
        assert t == norm(lxml.html.document_fromstring(html.read_text(encoding='utf-8')).body.text_content()), '텍스트 손실'
        pg = sec.find('.//' + HP + 'pagePr')
        m = pg.find(HP + 'margin')
        text_w = int(pg.get('width')) - int(m.get('left')) - int(m.get('right'))
        for tb in sec.iter(HP + 'tbl'):
            w = int(tb.find(HP + 'sz').get('width'))
            assert abs(w - text_w) <= text_w * 0.05, f'표 폭 {w} != 본문 폭 {text_w} (width:100%)'
        bf = {b.get('id'): [b.find(HH + n).get('type') for n in ('leftBorder', 'rightBorder', 'topBorder', 'bottomBorder')]
              for b in head.iter(HH + 'borderFill')}
        assert any(bf[c.get('borderFillIDRef')] != ['NONE'] * 4 for c in sec.iter(HP + 'tc')), '셀 테두리 없음(<style> 클래스 규칙 무시)'
        z = zipfile.ZipFile(tmp / 'b.hwpx')       # 사진 2장: pic + BinData + 매니페스트가 맞아야 한다
        pics = list(sec.iter(HP + 'pic')); bins = [n for n in z.namelist() if n.startswith('BinData/')]
        hpf = z.read('Contents/content.hpf').decode()
        assert len(pics) == len(bins) == 2 and all(f'href="{n}"' in hpf for n in bins), (len(pics), bins)
        for pc in pics:
            w = int(pc.find(HP + 'curSz').get('width'))
            assert 0 < w <= text_w, f'그림 폭 {w} > 본문 폭 {text_w}'
        hwpx2html.convert(str(tmp / 'b.hwpx'), str(tmp / 'b2.html'))
        assert (tmp / 'b2.html').read_text(encoding='utf-8').count('<img ') == 2, '왕복 후 이미지 손실'
        print('회의록 HTML OK', s, '| 그림', len(pics), bins)

        # 한컴 글머리(Wingdings 사설 영역 U+F09F)가 HTML에서 일반 '•'로 나와야 한다
        zin = zipfile.ZipFile(tmp / 'b.hwpx'); zout = zipfile.ZipFile(tmp / 'c.hwpx', 'w')
        for it in zin.infolist():
            d = zin.read(it.filename)
            zout.writestr(it, d.replace('•'.encode(), ''.encode()) if it.filename == 'Contents/section0.xml' else d)
        zout.close()
        hwpx2html.convert(str(tmp / 'c.hwpx'), str(tmp / 'c.html'))
        c = (tmp / 'c.html').read_text(encoding='utf-8')
        assert '' not in c and '•' in c, '글머리 사설 영역 문자 그대로 출력'
        print('글머리 변환 OK')

    import convert, os
    os.environ['HWP_CLI'] = 'off'      # 아래 기존 시험은 자체 변환 경로(HTML 을 거침) 기준. hwp-cli 경로는 따로 시험한다
    small = next((DATA / 'samples').glob('*근무계획서*.hwp'), None)
    if small:  # 통합 진입점: 내용으로 형식을 알아내 hwp->hwpx를 한 번에, 지원 안 하는 조합은 거부
        convert.convert(small, tmp / 'd.hwpx'); convert.convert(tmp / 'd.hwpx', tmp / 'd.html')
        assert [convert.detect(p) for p in (small, tmp / 'd.hwpx', tmp / 'd.html')] == ['hwp', 'hwpx', 'html']
        for bad in (tmp / 'x.hwp', tmp / 'x'):
            try: convert.convert(small, bad); raise AssertionError('지원 안 하는 변환을 통과시킴')
            except ValueError: pass
        print('convert.py OK')

        # 결재선: 문서 맨 위에 칸 이름 4개가 오고, 표가 정확히 1개 늘며(여백 칸 포함 한 표), HTML 로도 같다
        labels = ('담당', '검토', '확인', '승인')
        convert.convert(small, tmp / 'ap.hwpx', approval=labels); convert.convert(small, tmp / 'ap.html', approval=labels)
        sec, _ = parts(tmp / 'ap.hwpx'); s_ap, t_ap = stats(tmp / 'ap.hwpx'); s_no, t_no = stats(tmp / 'd.hwpx')
        assert t_ap.startswith(''.join(labels)) and t_ap.endswith(t_no), '결재선이 문서 맨 위에 안 들어감'
        assert s_ap['tbl'] == s_no['tbl'] + 1, (s_ap, s_no)
        assert (tmp / 'ap.html').read_text(encoding='utf-8').count('class="approval"') == 1
        print('결재선 OK')

        os.environ.pop('HWP_CLI', None)
        if convert.find_hwp_cli():      # hwp-cli 가 있는 곳에서만: HWP->HWPX 직접 변환, 글이 빠지지 않을 것, 결재선이면 자체 변환기로 바뀔 것, 끄기(off) 동작
            r = convert.convert(small, tmp / 'cli.hwpx'); assert r['engine'].startswith('hwp-cli') and zipfile.is_zipfile(tmp / 'cli.hwpx'), r
            assert len(stats(tmp / 'cli.hwpx')[1]) >= 0.95 * len(t_no), 'hwp-cli 결과에서 글이 빠짐'
            assert not convert.convert(small, tmp / 'cli_ap.hwpx', approval=labels)['engine'].startswith('hwp-cli'), '결재선인데 hwp-cli 를 썼음'
            os.environ['HWP_CLI'] = 'off'; assert not convert.convert(small, tmp / 'off.hwpx')['engine'].startswith('hwp-cli'), 'HWP_CLI=off 가 안 먹음'
            try: (tmp / 'bad.hwp').write_bytes(small.read_bytes()[:3000]); convert.convert(tmp / 'bad.hwp', tmp / 'bad.hwpx'); raise AssertionError('깨진 파일을 통과시킴')
            except ValueError as e: assert '손상' in str(e) or 'HWP' in str(e), e
            os.environ.pop('HWP_CLI', None); print('hwp-cli 경로 OK')

            # 떠 있는 개체 배치 복원: 공개 문서(exam_science)의 그림이 원본의 배치·기준·흐름 값으로 돌아오고, 그림 수와 ZIP 구조는 그대로
            pubdoc = DATA / 'corpus' / 'rhwp2' / 'exam_science.hwp'
            if pubdoc.exists():
                from lxml import etree
                r = convert.convert(pubdoc, tmp / 'pic.hwpx'); assert '그림' in r['engine'] and '배치 복원' in r['engine'], r
                with zipfile.ZipFile(tmp / 'pic.hwpx') as z:
                    assert z.namelist()[0] == 'mimetype' and z.getinfo('mimetype').compress_type == zipfile.ZIP_STORED and z.testzip() is None
                    pics = [p for n in z.namelist() if n.startswith('Contents/section') for p in etree.fromstring(z.read(n)).iter(convert.HP_NS + 'pic')]
                want = convert.src_objs(pubdoc)['pic']; assert len(pics) == len(want)
                for p, (w, h, a) in zip(pics, want):
                    pos = p.find(convert.HP_NS + 'pos')
                    if a & 1: continue
                    assert (p.get('textWrap'), pos.get('flowWithText'), pos.get('allowOverlap')) == (convert.OBJ_WRAP[a >> 21 & 7], str(a >> 13 & 1), str(a >> 14 & 1)), (a, dict(pos.attrib))
                assert any(p.get('textWrap') != 'IN_FRONT_OF_TEXT' for p in pics), '복원했는데도 전부 글 앞으로'
                print('개체 배치 복원 OK')

        if ('hwp', 'pdf') in convert.ROUTES:      # PDF 엔진(weasyprint)이 있는 곳(컨테이너)에서만 확인한다
            import base64
            r = convert.convert(small, tmp / 'd.pdf', approval=labels)
            assert (tmp / 'd.pdf').read_bytes()[:5] == b'%PDF-' and r['pages'] >= 1, r
            # 보안: 외부 그림(file://)은 PDF 에 들어가면 안 된다. data: 그림은 들어가야 한다(그걸로 검출이 되는지 먼저 확인).
            png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
            (tmp / 'secret.png').write_bytes(base64.b64decode(png))
            def pdf_has_image(src):      # HTML 은 하위 폴더에 두고 secret.png 는 그 밖(tmp)에 둔다: HTML 폴더 안의 파일은 읽지만 밖은 안 읽어야 한다
                (tmp / 'ih').mkdir(exist_ok=True)
                (tmp / 'ih' / 'i.html').write_text(f'<html><body><p>x</p><img src="{src}" width="50"></body></html>', encoding='utf-8')
                convert.convert(tmp / 'ih' / 'i.html', tmp / 'i.pdf')
                return b'/Subtype /Image' in (tmp / 'i.pdf').read_bytes()
            assert pdf_has_image('data:image/png;base64,' + png), 'data: 그림이 PDF 에 안 들어감(시험 전제 실패)'
            assert not pdf_has_image((tmp / 'secret.png').as_uri()), '외부(file://) 그림이 PDF 로 새어 들어감'
            print('PDF OK')

    # hwp-cli 가 뭉갠 개체 배치(그림·도형·표)를 원본 값으로 되돌리는 일(합성 HWPX 로, 샘플·hwp-cli 없이): 종류별로 짝짓고, 오프셋은 안 건드리고, 크기가 안 맞는 종류·글자처럼 취급은 손대지 않음
    import convert as cvt
    P = 'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"'
    POS = ('<hp:pos treatAsChar="0" flowWithText="0" allowOverlap="1" vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="4294966646" horzOffset="0"/>')
    def mk(path, shape_w=1000):
        body = (f'<hp:pic textWrap="IN_FRONT_OF_TEXT" groupLevel="0"><hp:sz width="22792" height="17094"/>{POS}</hp:pic>'
                f'<hp:rect textWrap="IN_FRONT_OF_TEXT" groupLevel="0"><hp:sz width="{shape_w}" height="500"/>{POS}</hp:rect>'
                f'<hp:tbl textWrap="TOP_AND_BOTTOM"><hp:sz width="5000" height="3000"/>{POS}</hp:tbl>')
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr(zipfile.ZipInfo('mimetype'), 'application/hwp+zip'); z.writestr('Contents/section0.xml', f'<?xml version="1.0" encoding="UTF-8" standalone="yes" ?><hp:sec {P}>{body}</hp:sec>', compress_type=zipfile.ZIP_DEFLATED)
    pic_a = 0x042a2210       # 안전관리 회의록의 그림: 자리 차지(1)·세로 기준 문단(2)·가로 기준 단(2)·흐름 켬(비트 13)·겹침 끔(비트 14)
    tbl_a = (3 << 21) | (2 << 3) | (3 << 8)      # 글 앞으로(3)·겹침 끔
    old = cvt.src_objs; cvt.src_objs = lambda s: {'pic': [(22792, 17094, pic_a)], 'shape': [(1000, 500, pic_a)], 'tbl': [(5000, 3000, tbl_a)]}
    def attrs(path):
        from lxml import etree
        with zipfile.ZipFile(path) as z: r = etree.fromstring(z.read('Contents/section0.xml'))
        return {k: (e.get('textWrap'), dict(e.find(cvt.HP_NS + 'pos').attrib)) for k in ('pic', 'rect', 'tbl') for e in r.iter(cvt.HP_NS + k)}
    try:
        mk(tmp / 'fp.hwpx'); assert cvt.fix_obj_pos('x.hwp', tmp / 'fp.hwpx') == {'pic': 1, 'shape': 1, 'tbl': 1}
        with zipfile.ZipFile(tmp / 'fp.hwpx') as z:
            assert z.namelist()[0] == 'mimetype' and z.getinfo('mimetype').compress_type == zipfile.ZIP_STORED
            assert z.read('Contents/section0.xml').decode('utf-8').startswith('<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>')
        at = attrs(tmp / 'fp.hwpx')
        for k in ('pic', 'rect'):      # 그림·도형: 배치·기준·흐름·겹침을 원본대로
            wrap, pos = at[k]; assert wrap == 'TOP_AND_BOTTOM' and (pos['flowWithText'], pos['allowOverlap'], pos['horzRelTo'], pos['vertRelTo']) == ('1', '0', 'COLUMN', 'PARA'), (k, at[k])
        wrap, pos = at['tbl']; assert wrap == 'IN_FRONT_OF_TEXT' and pos['allowOverlap'] == '0' and pos['flowWithText'] == '0' and pos['horzRelTo'] == 'PARA', at['tbl']      # 표는 배치·겹침만
        assert all(v[1]['vertOffset'] == '4294966646' for v in at.values()), '오프셋을 건드림(음수는 부호 없는 정수 그대로여야 한다)'
        mk(tmp / 'fq.hwpx', shape_w=9999)      # 도형만 크기가 다르면 도형은 그대로, 나머지는 복원
        assert cvt.fix_obj_pos('x.hwp', tmp / 'fq.hwpx') == {'pic': 1, 'tbl': 1}; assert attrs(tmp / 'fq.hwpx')['rect'][0] == 'IN_FRONT_OF_TEXT'
        cvt.src_objs = lambda s: {'pic': [(22792, 17094, pic_a | 1)], 'shape': [(1000, 500, pic_a | 1)], 'tbl': [(5000, 3000, tbl_a | 1)]}      # 모두 글자처럼 취급이면 파일을 다시 쓰지도 않는다
        mk(tmp / 'fr.hwpx'); before = (tmp / 'fr.hwpx').read_bytes(); assert cvt.fix_obj_pos('x.hwp', tmp / 'fr.hwpx') == {} and (tmp / 'fr.hwpx').read_bytes() == before
        cvt.src_objs = lambda s: {'pic': [(22792, 17094, pic_a)], 'shape': [(1000, 500, pic_a)], 'tbl': [(5000, 3000, tbl_a)]}      # OBJ_FIX=pic 이면 그림만 되돌리고 도형·표는 hwp-cli 값 그대로
        old_fix = cvt.OBJ_FIX; cvt.OBJ_FIX = ['pic']
        try: mk(tmp / 'fs.hwpx'); assert cvt.fix_obj_pos('x.hwp', tmp / 'fs.hwpx') == {'pic': 1} and attrs(tmp / 'fs.hwpx')['rect'][0] == 'IN_FRONT_OF_TEXT' and attrs(tmp / 'fs.hwpx')['tbl'][0] == 'TOP_AND_BOTTOM'
        finally: cvt.OBJ_FIX = old_fix
    finally: cvt.src_objs = old
    print('개체 배치 복원(합성) OK')

    s1 = DATA / 'corpus' / 'rhwp2' / 'issue4514' / 'sample1-repro.hwp'
    if s1.exists():      # 이미지 채움: 제목 번호 네모(BinData 1, 가운데 배치, 300dpi 92px = 22.08pt)가 칸 배경으로 나와야 한다
        cvt.convert(s1, tmp / 's1.html'); h = (tmp / 's1.html').read_text(encoding='utf-8')
        assert h.count('background-position:center;background-size:22.08pt 22.08pt') >= 3, '번호 네모 이미지 채움이 없음'
        print('이미지 채움 OK')

    fc = (HERE / 'fonts.conf').read_text(encoding='utf-8')      # 굴림체·돋움체는 고정폭 한글 글꼴(나눔고딕코딩, 한글 1.0em·공백 0.5em)로, 한글 폭 보정은 0
    assert all(f'<family>{n}</family><prefer><family>NanumGothicCoding</family>' in fc for n in ('굴림체', '돋움체', 'GulimChe', 'DotumChe')), '고정폭 글꼴 대체가 없음'
    assert cvt.hwp2html.hangul_delta('굴림체') == 0 and cvt.hwp2html.hangul_delta('돋움체') == 0 and cvt.hwp2html.hangul_delta('굴림') > 0
    print('고정폭 글꼴 OK')

    if ('html', 'pdf') in cvt.ROUTES:      # HTML -> PDF(핵심 기능): 옛 속성·같은 폴더 자원·넓은 내용 줄여 맞추기·폴더 밖/인터넷 차단 (PDF 엔진이 있는 곳에서만)
        try: import pymupdf
        except ImportError: pymupdf = None
        from PIL import Image
        hd = tmp / 'h2p'; (hd / 'res').mkdir(parents=True, exist_ok=True); (hd / 'sub').mkdir(exist_ok=True)
        Image.new('RGB', (40, 40), (200, 0, 0)).save(hd / 'res' / 'pic.png'); Image.new('RGB', (40, 40), (0, 0, 200)).save(hd / 'secret.png')
        (hd / 'res' / 'a.css').write_text('.r{font-size:30px}', encoding='utf-8')
        (hd / 'leg.html').write_text('<html><body><table border="1" cellpadding="8" width="60%"><tr><td>가</td><td>나</td></tr></table></body></html>', encoding='utf-8')
        (hd / 'res.html').write_text('<html><head><meta charset="utf-8"><link rel="stylesheet" href="res/a.css"></head><body><p class="r">글</p><img src="res/pic.png" width="40"></body></html>', encoding='utf-8')
        (hd / 'sub' / 'out.html').write_text('<html><body><p>밖</p><img src="../secret.png" width="40"><img src="http://example.invalid/x.png" width="40"></body></html>', encoding='utf-8')
        (hd / 'wide.html').write_text('<html><head><style>td{white-space:nowrap;border:1px solid #666}table{border-collapse:collapse}</style></head><body><table><tr>' + ''.join('<td>열%d값값값</td>' % c for c in range(1, 15)) + '</tr></table></body></html>', encoding='utf-8')
        for n in ('leg', 'res', 'out', 'wide'): cvt.convert(hd / ('sub/out.html' if n == 'out' else n + '.html'), tmp / ('h_' + n + '.pdf'))
        assert b'/Subtype /Image' in (tmp / 'h_res.pdf').read_bytes(), '같은 폴더 그림이 안 들어감'
        assert b'/Subtype /Image' not in (tmp / 'h_out.pdf').read_bytes(), '폴더 밖·인터넷 그림이 PDF 로 새어 들어감'
        if pymupdf:
            assert len(pymupdf.open(tmp / 'h_leg.pdf')[0].get_drawings()) >= 4, '옛 table border 속성이 안 먹음'
            assert max(s['size'] for b in pymupdf.open(tmp / 'h_res.pdf')[0].get_text('dict')['blocks'] for l in b.get('lines', []) for s in l['spans']) > 20, '같은 폴더 CSS 가 안 먹음'
            pg = pymupdf.open(tmp / 'h_wide.pdf'); assert len(pg) == 1 and max(d['rect'].x1 for d in pg[0].get_drawings()) <= pg[0].rect.width + 1, '넓은 표가 쪽에 안 맞음'
        print('HTML→PDF OK')

    gg = DATA / 'samples' / '공공기관 서식한글 개발 및 보급 계획.hwp'      # 그림 캡션이 빠지지 않을 것(우리 변환은 '< 구현 화면(예시) >' 글을 통째로 잃었다)
    if gg.exists():
        cvt.convert(gg, tmp / 'gg.html'); assert '구현화면(예시)' in re.sub(r'<[^>]+>|\s|&nbsp;', '', (tmp / 'gg.html').read_text(encoding='utf-8')), '그림 캡션이 빠짐'      # 글이 글꼴 칸별 span 으로 쪼개지니 태그·공백을 걷고 찾는다
        print('그림 캡션 OK')
    sj = DATA / 'samples' / '표준-공문-양식-한글-원본파일-1.hwp'      # 선 도형 SVG 는 viewBox 가 있어야 pt 좌표로 읽힌다(없으면 선 길이·굵기가 0.75배)
    if sj.exists():
        cvt.convert(sj, tmp / 'sj.html'); assert 'viewBox="0 0 ' in (tmp / 'sj.html').read_text(encoding='utf-8'), '선 SVG 에 viewBox 가 없음'
        print('선 도형 OK')
    bg = DATA / 'samples' / 'business-government-letter-01.hwp'      # 한글 -> 우리 HTML -> PDF 는 직통 PDF 와 같은 쪽 수여야 한다(HTML 에 줄·쪽 끝 정보를 hwp- 클래스로 담고 PDF 단계에서만 켠다)
    if bg.exists() and ('html', 'pdf') in cvt.ROUTES and ('hwp', 'pdf') in cvt.ROUTES:
        try: import pymupdf
        except ImportError: pymupdf = None
        cvt.convert(bg, tmp / 'bg.html'); bt = (tmp / 'bg.html').read_text(encoding='utf-8')
        assert 'class="hwp-ln' in bt, 'HTML 내보내기에 hwp-ln 표시가 없음'
        cvt.convert(tmp / 'bg.html', tmp / 'bg_via.pdf'); cvt.convert(bg, tmp / 'bg_direct.pdf')
        if pymupdf: assert len(pymupdf.open(tmp / 'bg_via.pdf')) == len(pymupdf.open(tmp / 'bg_direct.pdf')), '한글→HTML→PDF 쪽 수가 직통과 다름'
        print('한글→HTML→PDF OK')

    letter = next((DATA / 'samples').glob('business-government-letter-01.hwp'), None)
    if letter:   # HWP 양식 충실도(사용자가 가져온 업무서신): 칸별 테두리·세로 정렬·표 크기가 HTML 에 그대로 나와야 한다
        convert.convert(letter, tmp / 'l.html'); h = (tmp / 'l.html').read_text(encoding='utf-8')
        assert 'border-top:1mm solid #3366ff' in h, '파란 제목 선(1mm)이 없음'
        assert 'dotted' in h and 'border-left:none' in h, '점선 박스·선 없는 칸이 없음'
        assert 'vertical-align:middle' in h and 'vertical-align:top' not in h.split('<body>')[1].replace('display:inline-table;vertical-align:top', ''), '칸 세로 정렬이 가운데가 아님'
        assert 'width:473.41pt' in h, '표 크기가 문서에 저장된 값이 아님'
        assert '@page{size:595.28pt 841.88pt' in h, '쪽 설정이 반영 안 됨'
        print('HWP 양식 OK')

    gm = DATA / 'samples' / '공문서양식.hwp'
    if gm.exists():     # 머리말이 두 번 정의되면(앞: 로고, 뒤: 빈 머리말) 한컴은 뒤 정의를 쓴다 → 로고가 없어야 한다. U+F071 은 ❑ 로 나와야 한다
        convert.convert(gm, tmp / 'gm.html'); h = (tmp / 'gm.html').read_text(encoding='utf-8')
        assert 'position:running(hwphead)' not in h and '<img' not in h, '나중에 정의한 빈 머리말이 이겨야 하는데 로고가 나옴'
        assert '' not in h and '❑' in h, 'U+F071 이 ❑ 로 안 바뀜'
        assert '' not in h and '❍' in h and not convert.leftover_pua(tmp / 'gm.html'), 'U+F06D 가 ❍ 로 안 바뀜'
        print('HWP 머리말(나중 정의 우선)·❑ OK')

    f2, rq = DATA / 'corpus/rhwp/hwpx/hancom-hwp/form-002.hwp', DATA / 'corpus/rhwp/basic/request.hwp'
    if f2.exists() and rq.exists():     # 공개 시험 문서(corpus/, git 제외): 체크박스·자간·글꼴, 표 캡션, 글상자 글이 HTML 에 나와야 한다
        convert.convert(f2, tmp / 'f2.html'); h = (tmp / 'f2.html').read_text(encoding='utf-8')
        txt = re.sub(r'<[^>]+>', '', h)
        assert '☑ 혁신제품형' in txt and '☐ 원천기술형' in txt, '양식 컨트롤(체크박스)이 빠짐'
        assert re.search(r'letter-spacing:-0\.\d+em', h) and "font-family:'맑은 고딕',sans-serif" in h, '자간·글꼴이 반영 안 됨'
        convert.convert(rq, tmp / 'rq.html'); h = (tmp / 'rq.html').read_text(encoding='utf-8')
        assert 'colspan="8504"' not in h, '표 캡션을 칸으로 읽음(첫 줄이 깨짐)'
        assert '마일리지 카드 회원 가입 신청서' in h and '키홀더카드는' in h, '글상자 안의 글이 빠짐'
        print('HWP 컨트롤·캡션·글상자 OK')

    eng, sc, hy, cal = (DATA / 'corpus/rhwp/basic' / n for n in ('english.hwp', 'shortcut.hwp', 'Hyper(hwp2010).hwp', 'calendar_year.hwp'))
    if eng.exists() and sc.exists() and hy.exists() and cal.exists():     # 개요 번호, 다단·오른쪽 맞춤 탭·가로 쪽·띠 그라데이션, 바탕쪽 그림, 입력 상자·단추
        txt = lambda p: (convert.convert(p, tmp / 'x.html'), re.sub(r'<[^>]+>', '', (tmp / 'x.html').read_text(encoding='utf-8')))[1]
        t = txt(eng); assert re.search(r'\b1\.\s*우리말 번역', t) and re.search(r'\b15\.\s*우리말 번역', t), '개요 번호가 없음'
        convert.convert(sc, tmp / 's.html'); h = (tmp / 's.html').read_text(encoding='utf-8')
        assert 'column-count:2' in h and 'column-rule:' in h and 'class="tf"' in h and 'linear-gradient' in h, '다단·탭·그라데이션이 없음'
        assert '@page{size:841.88pt 595.28pt' in h, '가로 쪽이 반영 안 됨'
        convert.convert(hy, tmp / 'h.html'); h = (tmp / 'h.html').read_text(encoding='utf-8')
        assert h.count('class="mo"') + h.count('class="mo mm"') == 2 and h.count('<img') >= 4, '바탕쪽 그림이 없음'
        convert.convert(cal, tmp / 'c.html'); h = (tmp / 'c.html').read_text(encoding='utf-8')
        assert 'border:1px solid #7f7f7f' in h, '입력 상자·단추가 없음'
        assert 'class="hwp-footer hwp-run"' in h and h.count('class="hwp-footer"') == 1 and '.hwp-run,.hwp-pgn{display:none}' in h, '꼬리말이 본문 앞에도 있어야 PDF 의 모든 쪽에 되풀이된다(running 요소는 나온 쪽부터 쓸 수 있다)'
        assert h.index('class="hwp-footer hwp-run"') < h.index('class="hwp-footer"'), '시작 복사본이 끝 꼬리말보다 앞에 있어야 한다'
        print('HWP 번호·다단·탭·바탕쪽·양식 상자 OK')
        f2h = DATA / 'corpus/rhwp/hwpx/hancom-hwp/form-002.hwp'     # 쪽 번호: 한컴 PDF 가 아래 가운데에 "- 1 -" 을 찍는다(앞뒤 장식이 비면 줄표 기본 서식)
        if f2h.exists():
            convert.convert(f2h, tmp / 'f2h.html'); h = (tmp / 'f2h.html').read_text(encoding='utf-8')
            assert '@bottom-center{content:"- " counter(page,decimal) " -"' in h, '쪽 번호 서식이 한컴과 다름'
        print('HWP 쪽 번호 OK')

    # 입력 방어: 텍스트는 HTML 태그가 있어야 HTML이고, CP949 HTML도 변환되며, 압축 폭탄 상한이 걸린다
    (tmp / 'n.txt').write_text('그냥 메모입니다\n', encoding='utf-8')
    (tmp / 'k.html').write_bytes('<html><body><p>안녕 회의록</p></body></html>'.encode('cp949'))
    try: convert.detect(tmp / 'n.txt'); raise AssertionError('태그 없는 텍스트가 HTML로 통과')
    except ValueError: pass
    kind, why = convert.inspect(tmp / 'k.html'); assert kind == 'html' and '<html' in why, why
    convert.convert(tmp / 'k.html', tmp / 'k.hwpx')
    assert '안녕회의록' in norm(''.join(t.xpath('string(.)') for t in parts(tmp / 'k.hwpx')[0].iter(HP + 't'))), 'CP949 글자 손실'
    if src and small:       # 상한을 1000바이트로 낮춰, 진짜 1GB 파일 없이 거부 경로를 확인한다
        for mod, name, target in ((hwpx2html, 'MAX_ZIP_BYTES', src), (hwp2html, 'MAX_STREAM', small)):
            old = getattr(mod, name); setattr(mod, name, 1000)
            try: convert.convert(target, tmp / 'big.html'); raise AssertionError(f'{name} 상한이 안 걸림')
            except ValueError as e: assert '한도' in str(e), e
            finally: setattr(mod, name, old)
        print('입력 방어 OK')

    if html:        # 보조 평면 사설 문자(공고문의 겹낫표·화살표): 아는 것은 진짜 기호로, 모르는 것은 leftover_pua가 센다
        zin = zipfile.ZipFile(tmp / 'b.hwpx'); zout = zipfile.ZipFile(tmp / 'p.hwpx', 'w')
        for it in zin.infolist():
            d = zin.read(it.filename)
            zout.writestr(it, d.replace('•'.encode(), '\U000f0039\U000f0999'.encode()) if it.filename == 'Contents/section0.xml' else d)
        zout.close()
        convert.convert(tmp / 'p.hwpx', tmp / 'p.html')
        h = (tmp / 'p.html').read_text(encoding='utf-8')
        assert '⬅' in h and '\U000f0039' not in h, '보조 평면 사설 문자가 안 바뀜'
        assert convert.leftover_pua(tmp / 'p.html') == [0xF0999], '모르는 사설 문자를 못 셈'
        print('보조 평면 사설 문자 OK')
    # 표 행 나눔 판정(split_plan: (칸 높이, 안쪽 여백, 걸친 행 수, 저장된 글 높이) 목록 -> 높이를 뺄 '찬 큰 행'인가). 기본 꺼짐(SPLIT_ROWS=on)이지만 판정 규칙은 지킨다
    sp = hwp2html.split_plan
    assert sp([(300, 10, 1, 280)]) and sp([(300, 10, 1, 40), (300, 10, 1, 290)]), '글이 칸을 채운 큰 행은 높이를 빼야 한다'
    assert not sp([(300, 10, 1, 100)]), '글이 못 채운 행(빈 답안 칸)은 높이를 지켜야 한다'
    assert not sp([(287, 10, 1, 475)]), '글이 칸보다 훨씬 크면 줄 정보를 못 믿는다(근무계획서 287pt 칸에 475pt)'
    assert not sp([(60, 10, 1, 50)]), '작은 행은 건드리지 않는다'
    assert not sp([(300, 10, 2, 290)]) and not sp([(300, 10, 1, 0)]), '걸친 행·줄 정보 없음은 건드리지 않는다'
    print('표 행 나눔 판정 OK')
    # 표 제목 줄 반복(head_rows: 제목 셀이 맨 위 줄에 있고 '제목 줄 자동 반복'이 켜진 표만 thead)
    hr = hwp2html.head_rows
    row = lambda r, hd, rs=1: dict(row=r, rs=rs, hd=hd)
    assert hr(3, [row(0, 1), row(0, 1), row(1, 0), row(2, 0)], True) == 1, '맨 위 줄의 제목 셀은 제목 줄'
    assert hr(3, [row(0, 1), row(1, 1), row(2, 0)], True) == 2, '0~1 줄이 제목 셀이면 두 줄'
    assert hr(3, [row(0, 1), row(1, 0)], False) == 0, '제목 줄 자동 반복이 꺼졌으면 안 낸다'
    assert hr(3, [row(0, 0), row(1, 1)], True) == 0, '맨 위 줄이 제목 셀이 아니면(아래 줄만 제목 셀) 안 낸다'
    assert hr(2, [row(0, 1), row(1, 1)], True) == 0, '표가 제목 줄뿐이면 안 낸다'
    assert hr(3, [row(0, 1, 2), row(1, 0), row(2, 0)], True) == 0, '제목 줄 밖으로 걸친 칸이 있으면 안 낸다'
    if src:        # 공고문 HWPX(repeatHeader=1, 제목 셀 7개)는 thead 를 내고, 왕복해도 제목 셀 표시(header=1)가 남는다
        th = (tmp / 'a.html').read_text(encoding='utf-8')
        assert th.count('<thead>') >= 1 and th.count('<thead>') == th.count('</thead><tbody>') == th.count('</tbody>'), '제목 줄 반복 표가 thead/tbody 로 안 나옴'
        sx = zipfile.ZipFile(tmp / 'a.hwpx').read('Contents/section0.xml').decode('utf-8')
        assert sx.count(' header="1"') >= th.count('<thead>'), '왕복에서 제목 셀 표시가 사라짐'
    print('표 제목 줄 반복 OK')
    kr = hwp2html.keep_rows        # 쪽 경계에서 다음 줄과 안 갈라야 하는 줄: 걸친 칸 묶음(≤150pt)·낮은 첫 줄(≤30pt)
    assert kr([(1, 2, 139)], 0, 22.3) == {0, 1}, '제출 서류 표: 첫 줄 + 걸친 묶음의 윗줄'
    assert kr([(1, 2, 300)], 0, 22.3) == {0} and kr([(1, 2, 139)], 0, 120) == {1}, '큰 묶음·높은 첫 줄은 가를 수 있다'
    print('표 줄 붙이기 OK')
    hv = hwp2html.heavy_css      # 글꼴 자체가 굵은 글꼴(HY헤드라인M 등)은 '굵게' 속성이 없어도 굵게, 이미 굵거나 보통 글꼴은 그대로
    assert hv('HY헤드라인M', False) and hv('한양견고딕', False) and hv('HY울릉도B', False) and not hv('맑은 고딕', False) and not hv('HY울릉도M', False) and not hv('HY헤드라인M', True) and hv('한컴 소망 B', False) and not hv('한컴 소망 M', False) and not hv('한컴 바탕', False), '굵은 글꼴 판정'
    g = hwp2html.grad_css((90, ['#fff', '#cedeef'], 2, (50, 50)))      # 원형 그라데이션은 중심에서 가장 먼 모서리까지의 원, 선형은 HWP 각도 90 = 왼→오른쪽(CSS 90deg)
    assert g == 'radial-gradient(circle farthest-corner at 50% 50%,#fff,#cedeef)' and hwp2html.grad_css((90, ['#000', '#fff'], 1, (0, 0))).startswith('linear-gradient(90deg'), '그라데이션 CSS'
    assert hwp2html.family('HY헤드라인M').endswith("sans-serif,'NanumGothic'") and hwp2html.family('산세리프').endswith("sans-serif,'NanumGothic'") and hwp2html.family('휴먼명조').endswith("serif,'NanumMyeongjo'"), '글꼴 계열'
    assert hwp2html.family('Gulim').endswith("'NanumGothic'") and hwp2html.family('Haansoft Dotum').endswith("'NanumGothic'") and hwp2html.family('Verdana').endswith("'NanumMyeongjo'"), '영문 이름 고딕'      # 영문 이름 고딕이 명조로 찍히던 문제
    assert html2hwpx.families(hwp2html.family('Gulim').split(':', 1)[1]) == ['Gulim'] and html2hwpx.families("'맑은 고딕','Arial',sans-serif") == ['맑은 고딕', 'Arial'], '대체 글꼴 꼬리는 글꼴 이름이 아니다'
    assert hwp2html.hangul_delta('한컴 고딕') == 0.0 and hwp2html.hangul_delta('Haansoft Dotum') == 0.060 and hwp2html.hangul_delta('신명 중고딕') == hwp2html.GOTHIC_DELTA and hwp2html.hangul_delta('신명 중명조') == hwp2html.HANGUL_DELTA['한컴바탕'], '표 밖 글꼴 폭 보정'      # 한컴 고딕은 실측 0(예외), 한컴돋움 0.060(실측), 표 밖 고딕은 종류 기본값
    print('굵은 글꼴 OK')
    dot = chr(0x318d)
    assert hwp2html.mid_dot(f'<title>{dot}</title><style>.a{{}}</style><p>법령{dot}행정</p>') == f'<title>{dot}</title><style>.a{{}}</style><p>법령<span class="mid">{dot}</span>행정</p>', '가운뎃점 감싸기'
    print('가운뎃점 OK')
    # HTML 은 글꼴 폭 보정(--hd)을 따로 적어 letter-spacing 에 안 섞고, PDF 로 찍을 때만 더한다 / PDF 용 줄 꺾임 보정(어절 안 끊기·문단 끝 글자 간격 0)
    import re as _re
    assert hwp2html.spacing_css(0, 0.056) == ['--hd:0.056em'] and hwp2html.spacing_css(-0.05, 0.056) == ['letter-spacing:-0.05em', '--hd:0.056em;--ls:-0.05em'] and hwp2html.spacing_css(0, 0) == []
    if src:
        th = (tmp / 'a.html').read_text(encoding='utf-8')
        assert '--hd:' in th and not _re.search(r"font-family:'맑은 고딕'[^\"]*letter-spacing:0\.056em", th), '폭 보정이 letter-spacing 에 섞여 HTML 에 들어감'
    kw = convert._keep_words
    W = chr(0x2060)
    assert kw('<style>p{word-break:keep-all}</style><p>가나다 abc</p>') == '<style>p{word-break:keep-all}</style><p>가' + W + '나' + W + '다 abc</p>', '한글 글자 사이에 WJ'
    assert kw('<style>p{word-break:keep-all}</style><p style="word-break:break-all">가나</p><p>가나</p>').count(W) == 1, '글자 단위 줄 나눔 문단은 그대로'
    assert kw('<p>가나</p>') == '<p>가나</p>', 'keep-all 을 안 쓴 외부 HTML 은 그대로'
    t = convert._TAIL.sub(convert._tail_spacing, '<p><span style="font-size:10pt;--hd:0.056em;--ls:0.01em;letter-spacing:0.01em">[공급기업]</span></p>')
    assert t == '<p><span style="font-size:10pt;--hd:0.056em;--ls:0.01em;letter-spacing:0.01em">[공급기업</span><span style="font-size:10pt;letter-spacing:0">]</span></p>', t
    print('PDF 줄 꺾임 보정 OK')
    # 정렬된 떠 있는 개체 위치(float_aligned): 한컴 수능 시험지 값으로 — 가운데는 기준 영역 가운데+오프셋, 오른쪽·아래는 오프셋이 안쪽
    import struct as _st
    class _Ctl:
        def __init__(s, attr, vo, ho, w, h): s.p = _st.pack('<4sIiiII', b' osg', attr, round(vo * 100), round(ho * 100), round(w * 100), round(h * 100)) + bytes(20)
    A = lambda vrel, va, hrel, ha: 3 << 21 | vrel << 3 | va << 5 | hrel << 8 | ha << 10      # 글 앞으로(3) + 기준·정렬
    old_g = (list(hwp2html.PAGEG), list(hwp2html.PAGEM), hwp2html.NEST[0]); hwp2html.PAGEG[:] = [771.02, 1116.85, 666.14, 909.94]; hwp2html.PAGEM[:] = [52.44, 110.54]; hwp2html.NEST[0] = 0
    try:
        f = lambda *a: hwp2html.float_obj(_Ctl(*a))
        o = f(A(0, 0, 0, 1), 168.42, 1.05, 0.01, 850.39) % 'X'; assert '--cx:334.115pt;--cy:57.88pt' in o, o      # 종이 가운데 단 구분선: 771.02/2+1.05-52.44
        o = f(A(1, 0, 0, 2), 10, 52.03, 42.52, 42.52) % 'X'; assert '--cx:624.03pt;--cy:10pt' in o, o              # 종이 오른쪽 쪽 번호 상자: 771.02-42.52-52.03-52.44
        o = f(A(1, 2, 0, 0), 20, 0, 100, 40) % 'X'; assert '--cx:-52.44pt' in o and '--cy:%gpt' % (round(110.54 + 909.94 - 40 - 20 - 110.54, 2)) in o, o   # 쪽 기준 아래 정렬
        assert f(A(0, 0, 0, 2), 58.53, 52.03, 42.52, 42.52) is None      # 본문 위(머리말 자리)에 놓이는 쪽 기준 개체는 안 한다
        o = f(A(2, 0, 3, 1), 0, 0, 425.19, 56.69) % 'X'; assert 'left:50%;margin-left:-212.595pt' in o, o         # 문단 기준 가운데
        o = f(A(2, 0, 2, 2), 1.5, 3, 40, 10) % 'X'; assert 'right:3pt' in o, o                                       # 단 기준 오른쪽, 오프셋 안쪽
        assert f(A(0, 0, 0, 3), 0, 0, 10, 10) is None and f(A(2, 1, 3, 1), 0, 0, 10, 10) is None      # 안쪽·바깥쪽, 문단 기준 세로 가운데는 안 함
        hwp2html.NEST[0] = 1; assert f(A(1, 0, 0, 1), 0, 0, 10, 10) is None and f(A(2, 0, 3, 1), 0, 0, 10, 10) is not None      # 표·글상자 안: 종이·쪽 기준은 건너뛰고 문단 기준은 한다
        assert hwp2html.float_obj(_Ctl(3 << 21 | 2 << 3 | 2 << 8, 5, 6, 7, 8)) % 'X' == '<div style="position:relative;height:0"><div style="position:absolute;left:6pt;top:5pt">X</div></div>'      # 위·왼쪽 정렬은 예전 그대로
    finally: hwp2html.PAGEG[:], hwp2html.PAGEM[:], hwp2html.NEST[0] = old_g
    print('정렬 개체 위치 OK')

    # 그림 번호는 저장 id 가 아니라 DocInfo BIN_DATA 목록의 순번(1부터) — Worldcup_FIFA2010_32: 목록 순서 1~4·7~34·5·6
    old_bins = list(hwp2html.bins); hwp2html.bins[:] = [dict(id=i, ext='gif', comp=0) for i in (1, 2, 7, 5)]
    try:
        assert hwp2html.binfo(3)['id'] == 7 and hwp2html.binfo(4)['id'] == 5 and hwp2html.binfo(1)['id'] == 1
        for bad in (0, 5):
            try: hwp2html.binfo(bad); assert False, bad
            except IndexError: pass
    finally: hwp2html.bins[:] = old_bins
    # 묶음 개체 속 도형의 자리: 이동 행렬 · (확대·회전) 쌍 — Worldcup 제목 묶음(공 그림 (0,0)·65.62×66.07, 제목 글상자 (50.12,2.72)·801.17×50.3 → 오른쪽 끝 851.29 = 묶음 폭)
    import struct as _st
    def leaf(x, y, cw, ch, mats): return b'cip$' + _st.pack('<iiHHIIIIIhii', x, y, 1, 0, 0, 0, round(cw * 100), round(ch * 100), 0, 0, 0, 0) + _st.pack('<H', (len(mats) - 1) // 2) + b''.join(_st.pack('<6d', *m) for m in mats)
    I = (1, 0, 0, 0, 1, 0)
    assert hwp2html.leaf_box(leaf(-15375, -11198, 65.62, 66.07, [(1, 0, -15375, 0, 1, -11198), I, I, (0.265, 0, 15375, 0, 0.265, 11198), I])) == (0, 0, 65.62, 66.07)
    b = hwp2html.leaf_box(leaf(1060, 272, 801.17, 50.3, [(1, 0, 1060, 0, 1, 272), I, I, (1.55, 0, 3952, 0, 2.032, 0), I])); assert b == (50.12, 2.72, 801.17, 50.3), b
    assert hwp2html.leaf_box(leaf(0, 0, 10, 10, [I, I, (0, 1, 0, -1, 0, 0)])) is None      # 회전이 있으면 안 그린다
    print('그림 번호 순번·묶음 개체 OK')

    # 차트(OOXML -> SVG): 종류별 요소·잘못된 XML·못 그리는 종류는 None
    import chartsvg
    def cxml(kind, ser, extra='', title=''):
        mk = lambda tag, vs, ft: '<c:%s><c:%sRef><c:f>x</c:f><c:%sCache><c:ptCount val="%d"/>%s</c:%sCache></c:%sRef></c:%s>' % (tag, ft[:3], ft, len(vs), ''.join('<c:pt idx="%d"><c:v>%s</c:v></c:pt>' % (i, v) for i, v in enumerate(vs)), ft, ft[:3], tag)
        sers = ''.join('<c:ser><c:idx val="%d"/><c:tx><c:strRef><c:strCache><c:pt idx="0"><c:v>%s</c:v></c:pt></c:strCache></c:strRef></c:tx>%s%s</c:ser>' % (i, n, mk('cat', ['가', '나', '다'], 'strCache'), mk('val', v, 'numCache')) for i, (n, v) in enumerate(ser))
        return ('<c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><c:chart>%s<c:plotArea><c:%sChart>%s%s</c:%sChart></c:plotArea><c:legend><c:legendPos val="r"/></c:legend></c:chart></c:chartSpace>' % (title, kind, extra, sers, kind)).encode('utf-8')
    S = [('A', [1, 2, 3]), ('B', [3, 2, 1])]; cnt = lambda s, t: s.count('<' + t)
    s = chartsvg.render(cxml('pie', S[:1]), 300, 200); assert s.startswith('<svg') and cnt(s, 'path') == 3, s
    s = chartsvg.render(cxml('doughnut', S[:1]), 300, 200); assert cnt(s, 'path') == 3 and 'A' in s
    s = chartsvg.render(cxml('bar', S, '<c:barDir val="col"/><c:grouping val="clustered"/>'), 300, 200); assert cnt(s, 'rect') == 1 + 2 + 6 and '가' in s, cnt(s, 'rect')      # 바탕 1·범례 색 네모 2(계열 수)·막대 6
    s2 = chartsvg.render(cxml('bar', S, '<c:barDir val="bar"/><c:grouping val="stacked"/>'), 300, 200); assert s2 and s2 != s
    s = chartsvg.render(cxml('line', S), 300, 200); assert cnt(s, 'polyline') == 2 and cnt(s, 'circle') == 6
    s = chartsvg.render(cxml('area', S), 300, 200); assert cnt(s, 'polygon') == 2
    s = chartsvg.render(cxml('stock', [('고가', [5, 6, 7]), ('저가', [1, 2, 3]), ('종가', [3, 4, 5])], '<c:hiLowLines/>'), 300, 200); assert cnt(s, 'line') >= 3 + 3 + 3, cnt(s, 'line')
    s = chartsvg.render(cxml('pie', S[:1], title='<c:title/>'), 300, 200); assert '차트 제목' not in s and '>A<' in s      # 제목에 글이 없고 계열이 1개면 그 이름
    s = chartsvg.render(cxml('pie', S[:1]) .replace(b'<c:pie', b'<c:radar').replace(b'</c:pie', b'</c:radar'), 300, 200); assert s is None      # 못 그리는 종류
    assert chartsvg.render(b'<not xml', 300, 200) is None and chartsvg.render(cxml('pie', S[:1]), 0, 200) is None
    print('차트 SVG OK')

    # 벡터 그림: WMF 는 SVG 로 바꾸고, SVG 는 그대로, 위험한 SVG 는 거절한다. 그림 효과(회색조·흑백·밝기)
    import wmf2svg, struct as _st
    def rec(fn, *ints, raw=b''):
        body = b''.join(_st.pack('<h', v) for v in ints) + raw
        return _st.pack('<IH', 3 + len(body) // 2, fn) + body
    wmf = (_st.pack('<HHHIHIH', 1, 9, 0x300, 0, 2, 0, 0) + rec(0x020C, 30, 40) + rec(0x020B, 0, 0)
           + rec(0x02FA, 0, 1, 0, raw=_st.pack('<I', 0x0000FF)) + rec(0x02FC, 0, raw=_st.pack('<IH', 0x00FF00, 0)) + rec(0x012D, 0) + rec(0x012D, 1)
           + rec(0x0324, 3, 0, 0, 40, 0, 20, 30) + rec(0x0A32, 12, 5, 4, 0, raw='한글'.encode('cp949')) + _st.pack('<IH', 3, 0))
    sv = wmf2svg.wmf_to_svg(wmf)
    assert sv and sv.startswith('<svg') and 'viewBox="0 0 40 30"' in sv and '<polygon points="0,0 40,0 20,30"' in sv and 'stroke="#ff0000"' in sv and 'fill="#00ff00"' in sv and '>한글<' in sv, sv
    assert wmf2svg.wmf_to_svg(b'not a wmf' * 5) is None and wmf2svg.vector_svg(wmf, 'wmf').startswith('<svg')
    ok_svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="5" height="5"/></svg>'
    assert wmf2svg.vector_svg(ok_svg, 'svg') == ok_svg.decode()
    for bad in (b'<svg><script>1</script></svg>', b'<!DOCTYPE svg [<!ENTITY a "x">]><svg/>', b'<svg><foreignObject/></svg>', b'<svg><image href="http://x/y.png"/></svg>'):
        assert wmf2svg.vector_svg(bad, 'svg') is None, bad
    assert wmf2svg.vector_svg(bytes.fromhex('89504e470d0a1a0a'), 'png') is None      # 래스터는 PIL 이 맡는다
    from PIL import Image as _I
    px = lambda im, xy=(0, 0): im.getpixel(xy)
    im = _I.new('RGB', (2, 1)); im.putpixel((0, 0), (200, 100, 50)); im.putpixel((1, 0), (255, 255, 0))
    assert px(hwp2html.effect_image(im, 0, 0, 0)) == (200, 100, 50)      # 효과 없음은 그대로
    assert len(set(px(hwp2html.effect_image(im, 0, 0, 1)))) == 1      # 회색조: R=G=B
    bw = hwp2html.effect_image(im, 0, 0, 2); assert px(bw) == (0, 0, 0) and px(bw, (1, 0)) == (255, 255, 255)      # 흑백: 밝기 124 는 검정, 226 은 흰색
    g = _I.new('RGB', (1, 1), (100, 100, 100)); assert abs(px(hwp2html.effect_image(g, 20, 0, 0))[0] - 151) <= 1      # 밝기 +20: 100/255+0.2 → 151
    ra = _I.new('RGBA', (1, 1), (10, 20, 30, 128)); assert px(hwp2html.effect_image(ra, 0, 0, 1))[3] == 128      # 투명도 유지
    big = _I.new('RGB', (200, 100)); assert hwp2html.crop_image(big, 0, 0, 200 * 75, 100 * 75) is big      # 전체 영역이면 그대로(이미 잘린 그림)
    assert hwp2html.crop_image(big, 50 * 75, 20 * 75, 150 * 75, 70 * 75).size == (100, 50)      # 75 HWPUNIT = 1px 로 잘라낸다
    assert hwp2html.crop_image(big, 0, 0, 0, 0) is big and hwp2html.crop_image(big, 300 * 75, 0, 400 * 75, 100 * 75) is big      # 비었거나 그림 밖이면 그대로
    print('벡터 그림·그림 효과·그림 자르기 OK')

    # 자기 설명(--capabilities): JSON 으로 나오고, 한도가 app.py 의 값과 같고, 길 표와 맞는다
    import json as _json, subprocess as _sp, sys as _sys
    cap = convert.capabilities()
    assert {(r['from'], r['to']) for r in cap['routes']} == set(convert.ROUTES) and ('hwp', 'hwpx') in convert.ROUTES, '길 표와 다름'
    app_src = (HERE / 'app.py').read_text(encoding='utf-8')
    assert f"TIMEOUT = {cap['limits']['convert_timeout_seconds']} " in app_src and f"MAX_PARALLEL = {cap['limits']['parallel_conversions']} " in app_src, 'app.py 한도와 다름'
    r = _sp.run([_sys.executable, str(HERE / 'convert.py'), '--capabilities'], capture_output=True, encoding='utf-8')
    assert r.returncode == 0 and _json.loads(r.stdout)['name'] == 'file-conversation', r.stderr
    print('capabilities OK')


if __name__ == '__main__':
    demo()

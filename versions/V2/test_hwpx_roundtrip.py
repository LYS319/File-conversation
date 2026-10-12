"""HWPX<->HTML 변환기 회귀 점검 (API 호출 없음). python test_hwpx_roundtrip.py"""
import difflib, re, tempfile, zipfile
from pathlib import Path
import lxml.html
from lxml import etree
import hwp2html, hwpx2html, html2hwpx

HP = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'
HH = '{http://www.hancom.co.kr/hwpml/2011/head}'
HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1]          # samples/ · results/ 가 있는 프로젝트 루트 (이 파일은 versions/V2/ 안에 있다)
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
            r = convert.convert(small, tmp / 'cli.hwpx'); assert r.get('engine') == 'hwp-cli' and zipfile.is_zipfile(tmp / 'cli.hwpx'), r
            assert len(stats(tmp / 'cli.hwpx')[1]) >= 0.95 * len(t_no), 'hwp-cli 결과에서 글이 빠짐'
            assert 'engine' not in convert.convert(small, tmp / 'cli_ap.hwpx', approval=labels), '결재선인데 hwp-cli 를 썼음'
            os.environ['HWP_CLI'] = 'off'; assert 'engine' not in convert.convert(small, tmp / 'off.hwpx'), 'HWP_CLI=off 가 안 먹음'
            try: (tmp / 'bad.hwp').write_bytes(small.read_bytes()[:3000]); convert.convert(tmp / 'bad.hwp', tmp / 'bad.hwpx'); raise AssertionError('깨진 파일을 통과시킴')
            except ValueError as e: assert '손상' in str(e) or 'HWP' in str(e), e
            os.environ.pop('HWP_CLI', None); print('hwp-cli 경로 OK')

        if ('hwp', 'pdf') in convert.ROUTES:      # PDF 엔진(weasyprint)이 있는 곳(컨테이너)에서만 확인한다
            import base64
            r = convert.convert(small, tmp / 'd.pdf', approval=labels)
            assert (tmp / 'd.pdf').read_bytes()[:5] == b'%PDF-' and r['pages'] >= 1, r
            # 보안: 외부 그림(file://)은 PDF 에 들어가면 안 된다. data: 그림은 들어가야 한다(그걸로 검출이 되는지 먼저 확인).
            png = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
            (tmp / 'secret.png').write_bytes(base64.b64decode(png))
            def pdf_has_image(src):
                (tmp / 'i.html').write_text(f'<html><body><p>x</p><img src="{src}" width="50"></body></html>', encoding='utf-8')
                convert.convert(tmp / 'i.html', tmp / 'i.pdf')
                return b'/Subtype /Image' in (tmp / 'i.pdf').read_bytes()
            assert pdf_has_image('data:image/png;base64,' + png), 'data: 그림이 PDF 에 안 들어감(시험 전제 실패)'
            assert not pdf_has_image((tmp / 'secret.png').as_uri()), '외부(file://) 그림이 PDF 로 새어 들어감'
            print('PDF OK')

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
        assert h.count('class="mo"') == 2 and h.count('<img') >= 4, '바탕쪽 그림이 없음'
        convert.convert(cal, tmp / 'c.html'); h = (tmp / 'c.html').read_text(encoding='utf-8')
        assert 'border:1px solid #7f7f7f' in h, '입력 상자·단추가 없음'
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


if __name__ == '__main__':
    demo()

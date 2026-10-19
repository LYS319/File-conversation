"""HWPX<->HTML 변환기 회귀 점검 (API 호출 없음). python test_hwpx_roundtrip.py"""
import difflib, re, tempfile, zipfile
from pathlib import Path
import lxml.html
from lxml import etree
import hwp2html, hwpx2html, html2hwpx

HP = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'
HH = '{http://www.hancom.co.kr/hwpml/2011/head}'
HERE = Path(__file__).parent
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
    src = next((HERE / 'samples').glob('*.hwpx'), None)
    if src:  # 공고문 왕복: 문단·표·셀 수가 같아야 한다
        hwpx2html.convert(str(src), str(tmp / 'a.html'))
        html2hwpx.build(str(tmp / 'a.html'), str(tmp / 'a.hwpx'))
        (s0, t0), (s1, t1) = stats(src), stats(tmp / 'a.hwpx')
        assert s0 == s1 == dict(p=773, tbl=42, tc=472), (s0, s1)
        r = difflib.SequenceMatcher(None, t0.translate(hwp2html.PUA), t1, autojunk=False).ratio()   # 사설 영역 문자는 진짜 기호로 바뀌는 게 정상이라 원본에도 같은 표를 적용
        assert r >= 0.9998, r  # 자동번호 문단 1곳이 글자 '1.'로 바뀌는 것만 허용
        print('공고문 왕복 OK', s1, round(r, 5))

    html = next((HERE / 'results/V2_채팅에서_만든_HTML').glob('*회의록*.html'), None)
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

    import convert
    small = next((HERE / 'samples').glob('*근무계획서*.hwp'), None)
    if small:  # 통합 진입점: 내용으로 형식을 알아내 hwp->hwpx를 한 번에, 지원 안 하는 조합은 거부
        convert.convert(small, tmp / 'd.hwpx'); convert.convert(tmp / 'd.hwpx', tmp / 'd.html')
        assert [convert.detect(p) for p in (small, tmp / 'd.hwpx', tmp / 'd.html')] == ['hwp', 'hwpx', 'html']
        for bad in (tmp / 'x.hwp', tmp / 'x'):
            try: convert.convert(small, bad); raise AssertionError('지원 안 하는 변환을 통과시킴')
            except ValueError: pass
        print('convert.py OK')

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


if __name__ == '__main__':
    demo()

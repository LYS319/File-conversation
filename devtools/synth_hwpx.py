"""합성 HWPX 시험 문서 생성기(V3 1단계 검증용). 한컴이 이 문서를 열어 저장하면 저장된 줄(PARA_LINE_SEG) = 한컴의 줄 끊김 정답이 된다.
문단마다 글자 모양·문단 모양(한글 줄 나눔 기준 KEEP_WORD/BREAK_WORD, 왼쪽·오른쪽 여백, 들여쓰기, 정렬)을 달리 지정한다. 줄 폭은 문단 오른쪽 여백으로 바꾼다
(쪽 글 폭 = TEXT_W − 왼쪽 − 오른쪽). 저장된 줄(linesegarray)은 일부러 넣지 않는다 → 한컴이 새로 계산한다.
    from synth_hwpx import build; build([dict(text='가나다', face='함초롬바탕', size=10, ku=1, right=1000)], 'out.hwpx')
문단 필드: text, face(한글 칸 글꼴)·face_latin(없으면 face)·size(pt)·ratio·spacing·bold, ku(1 글자 단위 = HWPX KEEP_WORD, 0 어절 단위 = BREAK_WORD), left·right·intent(HWPUNIT), align.
"""
import re, sys, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import html2hwpx

TEXT_W = 42520      # 기본 쪽(A4, 좌우 여백 8504)의 글 폭 HWPUNIT
LANGS = ('HANGUL', 'LATIN', 'HANJA', 'JAPANESE', 'OTHER', 'SYMBOL', 'USER')
KEYS = ('hangul', 'latin', 'hanja', 'japanese', 'other', 'symbol', 'user')
FONT_TMPL = '<hh:font id="{i}" face="{f}" type="TTF" isEmbedded="0"><hh:typeInfo familyType="FCAT_GOTHIC" weight="6" proportion="4" contrast="0" strokeVariation="1" armStyle="1" letterform="1" midline="1" xHeight="1"/></hh:font>'


def _esc(t): return t.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def build(paras, out, page_w=None, page_h=None):
    base = Path(out).with_suffix('.base.hwpx')
    html = base.with_suffix('.html'); html.write_text('<html><body><p style="font-size:10pt">x</p></body></html>', encoding='utf-8')
    html2hwpx.build(str(html), str(base)); html.unlink()
    zin = zipfile.ZipFile(base); files = {n: zin.read(n) for n in zin.namelist()}; zin.close(); base.unlink()
    hd = files['Contents/header.xml'].decode('utf-8'); sec = files['Contents/section0.xml'].decode('utf-8')
    # 글꼴 목록: 쓰는 글꼴을 모든 언어 칸에 같은 번호로 넣는다
    faces = []
    for p in paras:
        for f in (p.get('face', '함초롬바탕'), p.get('face_latin') or p.get('face', '함초롬바탕')):
            if f not in faces: faces.append(f)
    ff = ''.join('<hh:fontface lang="%s" fontCnt="%d">%s</hh:fontface>' % (l, len(faces), ''.join(FONT_TMPL.format(i=i, f=f) for i, f in enumerate(faces))) for l in LANGS)
    hd = re.sub(r'<hh:fontfaces itemCnt="7">.*?</hh:fontfaces>', lambda m: '<hh:fontfaces itemCnt="7">%s</hh:fontfaces>' % ff, hd, flags=re.S)
    cp0 = re.search(r'<hh:charPr id="0".*?</hh:charPr>', hd, re.S).group(0)
    pp0 = re.search(r'<hh:paraPr id="0".*?</hh:paraPr>', hd, re.S).group(0)
    cids, pids, cps, pps = {}, {}, [], []
    body = []
    for n, p in enumerate(paras):
        fh, fl = p.get('face', '함초롬바탕'), p.get('face_latin') or p.get('face', '함초롬바탕')
        ck = (fh, fl, p.get('size', 10), p.get('ratio', 100), p.get('spacing', 0), bool(p.get('bold')))
        if ck not in cids:
            c = cp0.replace('id="0"', 'id="%d"' % len(cids), 1).replace('height="1000"', 'height="%d"' % round(ck[2] * 100), 1)
            c = re.sub(r'<hh:fontRef [^>]*/>', '<hh:fontRef hangul="%d" latin="%d" hanja="%d" japanese="%d" other="%d" symbol="%d" user="%d"/>' % ((faces.index(fh), faces.index(fl)) + (faces.index(fh),) * 5), c)
            c = re.sub(r'<hh:ratio [^>]*/>', '<hh:ratio ' + ' '.join('%s="%d"' % (k, ck[3]) for k in KEYS) + '/>', c)
            c = re.sub(r'<hh:spacing [^>]*/>', '<hh:spacing ' + ' '.join('%s="%d"' % (k, ck[4]) for k in KEYS) + '/>', c)
            if ck[5]: c = c.replace('<hh:underline', '<hh:bold/><hh:underline', 1)
            cids[ck] = len(cids); cps.append(c)
        pk = (p.get('ku', 1), p.get('left', 0), p.get('right', 0), p.get('intent', 0), p.get('align', 'JUSTIFY'), p.get('condense', 0), p.get('latin_break', 'KEEP_WORD'), p.get('tab', 0))
        if pk not in pids:
            q = pp0.replace('id="0"', 'id="%d"' % len(pids), 1)
            q = q.replace('breakNonLatinWord="KEEP_WORD"', 'breakNonLatinWord="%s"' % ('KEEP_WORD' if pk[0] else 'BREAK_WORD'), 1).replace('breakLatinWord="KEEP_WORD"', 'breakLatinWord="%s"' % pk[6], 1)
            q = q.replace('<hh:align horizontal="JUSTIFY"', '<hh:align horizontal="%s"' % pk[4], 1).replace('condense="0"', 'condense="%d"' % pk[5], 1)
            q = q.replace('tabPrIDRef="0"', 'tabPrIDRef="%d"' % pk[7], 1)
            for tag, v in (('intent', pk[3]), ('left', pk[1]), ('right', pk[2])): q = re.sub(r'<hc:%s value="[^"]*"' % tag, '<hc:%s value="%d"' % (tag, v), q)
            pids[pk] = len(pids); pps.append(q)
        text = p['text']
        body.append('<hp:p id="%d" paraPrIDRef="%d" styleIDRef="0" pageBreak="0" columnBreak="0" merged="0"><hp:run charPrIDRef="%d"><hp:t>%s</hp:t></hp:run></hp:p>' % (1000 + n, pids[pk], cids[ck], _esc(text)))
    hd = re.sub(r'<hh:charProperties itemCnt="1">.*?</hh:charProperties>', lambda m: '<hh:charProperties itemCnt="%d">%s</hh:charProperties>' % (len(cps), ''.join(cps)), hd, flags=re.S)
    hd = re.sub(r'<hh:paraProperties itemCnt="1">.*?</hh:paraProperties>', lambda m: '<hh:paraProperties itemCnt="%d">%s</hh:paraProperties>' % (len(pps), ''.join(pps)), hd, flags=re.S)
    # 구역: 첫 문단(구역 정의가 든 것)의 글은 비우고 시험 문단을 잇는다
    sec = re.sub(r'<hp:t>[^<]*</hp:t>', '<hp:t></hp:t>', sec, count=1)
    if page_w: sec = re.sub(r'(<hp:pagePr [^>]*?)width="\d+"', lambda m: m.group(1) + 'width="%d"' % page_w, sec, count=1)
    if page_h: sec = re.sub(r'(<hp:pagePr [^>]*?)height="\d+"', lambda m: m.group(1) + 'height="%d"' % page_h, sec, count=1)
    sec = sec.replace('</hs:sec>', ''.join(body) + '</hs:sec>')
    files['Contents/header.xml'] = hd.encode('utf-8'); files['Contents/section0.xml'] = sec.encode('utf-8')
    with zipfile.ZipFile(out, 'w') as z:
        z.writestr(zipfile.ZipInfo('mimetype'), files.pop('mimetype'), compress_type=zipfile.ZIP_STORED)
        for k, v in files.items(): z.writestr(k, v, zipfile.ZIP_DEFLATED)
    return out


if __name__ == '__main__':
    out = build([dict(text='가나다라마바사 ' * 12, face='함초롬바탕', size=10, ku=1, right=20000), dict(text='가나다라마바사 ' * 12, face='함초롬바탕', size=10, ku=0, right=20000)], sys.argv[1] if len(sys.argv) > 1 else 'synth_test.hwpx')
    print('만듦', out)

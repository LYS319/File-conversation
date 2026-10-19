"""HWPX 문단마다 '한컴이 저장한 높이'(다음 문단 줄 위치 - 이 문단 줄 위치, linesegarray)와 '우리가 그린 높이'(그 문단만 WeasyPrint 로 그린 높이)를 비교한다.
어느 종류의 문단이 한컴보다 크게 그려지는지 찾는 용도. 컨테이너에서: python para_heights.py 문서.hwpx [상위 개수]
주의: 저장된 줄 위치가 낡은 파일은 비교가 틀린다(vertsize 0)."""
import sys, zipfile
sys.path.insert(0, '/work')
import hwpx2html as X, weasyprint
from weasyprint.urls import URLFetcher
from lxml import etree

HP = X.HP
f = sys.argv[1]; top = int(sys.argv[2]) if len(sys.argv) > 2 else 14
head, secs = X.load(f); cv = X.Conv(head); cv.z = zipfile.ZipFile(f)
cv.bin_href = {i.get('id'): i.get('href') for i in etree.fromstring(cv.z.read('Contents/content.hpf')).iter('{http://www.idpf.org/2007/opf/}item') if (i.get('href') or '').startswith('BinData/')}
paras = [p for sec in secs for p in sec.findall(HP + 'p')]
cv.paragraph(paras[0], top=True); cv.pend = None; pg = cv.page
css = (f"@page{{size:{X.pt(pg['w'])} 4000pt;margin:0 {X.pt(pg['right'])} 0 {X.pt(pg['left'])}}} body{{margin:0}} p,div{{margin:0;orphans:1;widows:1}} "
       "p,div,td{white-space:pre-wrap;word-break:keep-all;overflow-wrap:break-word} td>p,td>div{white-space:pre-wrap} td{box-sizing:border-box}")


def height(html):
    doc = weasyprint.HTML(string=f'<html><head><meta charset="utf-8"><style>{css}</style></head><body>{html}</body></html>', url_fetcher=URLFetcher(allowed_protocols=('data',))).render()
    return doc.pages[0]._page_box.children[0].children[0].margin_height() * 0.75      # WeasyPrint 내부 단위는 CSS px(96dpi) -> pt


res = []
for i, p in enumerate(paras):
    sg = p.find(HP + 'linesegarray'); v0 = int(sg[0].get('vertpos')) if sg is not None and len(sg) else None
    n = paras[i + 1].find(HP + 'linesegarray') if i + 1 < len(paras) else None; nv = int(n[0].get('vertpos')) if n is not None and len(n) else None
    stored = (nv - v0) / 100 if v0 is not None and nv is not None and nv > v0 else None
    try: h = height(cv.paragraph(p, top=True))
    except Exception: h = None
    cv.pend = None
    res.append((i, stored, h, len(list(p.iter(HP + 'tbl'))), ''.join(p.itertext()).strip()[:18]))
ok = [r for r in res if r[1] and r[2]]
print('문단', len(res), '비교 가능', len(ok))
print('저장 높이 합 %.0fpt, 우리 높이 합 %.0fpt, 비 %.3f' % (sum(r[1] for r in ok), sum(r[2] for r in ok), sum(r[2] for r in ok) / sum(r[1] for r in ok)))
for r in sorted(ok, key=lambda r: -(r[2] - r[1]))[:top]: print(f'  #{r[0]} 저장 {r[1]:.1f} 우리 {r[2]:.1f} 차 {r[2] - r[1]:+.1f} 표{r[3]} {r[4]!r}')
if len(sys.argv) > 3:
    print('글만 비율 큰 것')
    for r in sorted([r for r in ok if r[3] == 0 and r[1] > 10], key=lambda r: -(r[2] / r[1]))[:int(sys.argv[3])]: print(f'  #{r[0]} 저장 {r[1]:.1f} 우리 {r[2]:.1f} 비 {r[2] / r[1]:.2f} {r[4]!r}')
for nm, fl in (('글만', lambda r: r[3] == 0), ('표 포함', lambda r: r[3] > 0)):
    s = [r for r in ok if fl(r)]; print(nm, len(s), '저장 %.0f 우리 %.0f 비 %.3f' % (sum(r[1] for r in s), sum(r[2] for r in s), sum(r[2] for r in s) / max(1, sum(r[1] for r in s))))

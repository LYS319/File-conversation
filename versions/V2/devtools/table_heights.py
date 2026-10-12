"""HWPX 표마다 한컴이 저장한 표 높이(sz.height)와 우리가 그린 높이(표만 따로 그린 높이)를 비교한다. 컨테이너에서: python table_heights.py 문서.hwpx [상위 개수]"""
import sys, zipfile
sys.path.insert(0, '/work')
import hwpx2html as X, weasyprint
from lxml import etree

HP = X.HP; f = sys.argv[1]; top = int(sys.argv[2]) if len(sys.argv) > 2 else 15
head, secs = X.load(f); cv = X.Conv(head); cv.z = zipfile.ZipFile(f); cv.bin_href = {}
paras = [p for sec in secs for p in sec.findall(HP + 'p')]
cv.paragraph(paras[0], top=True); cv.pend = None; pg = cv.page
css = (f"@page{{size:{X.pt(pg['w'])} 3000pt;margin:0 {X.pt(pg['right'])} 0 {X.pt(pg['left'])}}} body{{margin:0}} p,div{{margin:0;orphans:1;widows:1}} "
       "p,div,td{white-space:pre-wrap;word-break:keep-all;overflow-wrap:break-word} td{box-sizing:border-box}")


def height(html):
    # 셀 안 쪽 나눔은 끈다(무한히 높은 쪽에서는 행이 쪽 끝까지 늘어나 측정이 틀어진다)
    html = html.replace('break-before:page', '')
    doc = weasyprint.HTML(string=f'<html><head><meta charset="utf-8"><style>{css}</style></head><body>{html}</body></html>').render()
    return doc.pages[0]._page_box.children[0].children[0].margin_height() * 0.75


res = []
for i, p in enumerate(paras):
    for k, t in enumerate(p.iter(HP + 'tbl')):
        if t.getparent() is not None and any(a.tag == HP + 'tc' for a in t.iterancestors()): continue      # 안쪽 표는 건너뜀
        want = int(t.find(HP + 'sz').get('height')) / 100
        try: got = height(cv.table(t))
        except Exception: got = None
        res.append((i, k, want, got, t.get('rowCnt'), t.get('colCnt'), ''.join(t.itertext()).strip()[:16]))
ok = [r for r in res if r[3] and r[3] < 2900]
print('최상위 표', len(res), '비교 가능', len(ok), '| 한컴 합 %.0fpt 우리 합 %.0fpt 비 %.3f' % (sum(r[2] for r in ok), sum(r[3] for r in ok), sum(r[3] for r in ok) / sum(r[2] for r in ok)))
for r in sorted(ok, key=lambda r: -(r[3] - r[2]))[:top]: print(f'  문단#{r[0]} 표{r[1]} {r[4]}x{r[5]} 한컴 {r[2]:.1f} 우리 {r[3]:.1f} 차 {r[3] - r[2]:+.1f} {r[6]!r}')
print('3000pt 초과(측정 불가):', [(r[0], r[1]) for r in res if not r[3] or r[3] >= 2900])

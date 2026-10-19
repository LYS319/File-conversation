import sys, pymupdf, re
a = pymupdf.open(sys.argv[1]); b = pymupdf.open(sys.argv[2])
norm = lambda s: re.sub(r'\s+', '', s)
A = [norm(p.get_text()) for p in a]; B = [norm(p.get_text()) for p in b]
# 한컴 각 쪽의 본문 첫머리(쪽 번호 "-N-" 뒤 24자)를 앵커로, 우리 PDF 의 어느 쪽에 처음 나오는지 찾는다
res = []
for i, t in enumerate(A):
    t2 = re.sub(r'^-\d+-', '', t)[:22]
    hits = [j + 1 for j, u in enumerate(B) if t2 in u]
    res.append((i + 1, t2, hits[:3]))
for r in res: print(r)

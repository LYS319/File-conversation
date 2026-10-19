import sys, io, pymupdf
from PIL import Image
# 사용: montage.py 출력.png 배율 pdf:쪽 pdf:쪽 ...   (쪽은 1부터)
out, z, specs = sys.argv[1], float(sys.argv[2]), sys.argv[3:]
ims = []
for s in specs:
    f, n = s.rsplit(':', 1); d = pymupdf.open(f)
    ims.append(Image.open(io.BytesIO(d[int(n) - 1].get_pixmap(matrix=pymupdf.Matrix(z, z)).tobytes('png'))).convert('RGB'))
W = sum(i.width for i in ims) + 8 * (len(ims) - 1); H = max(i.height for i in ims)
m = Image.new('RGB', (W, H), (200, 200, 200)); x = 0
for i in ims: m.paste(i, (x, 0)); x += i.width + 8
m.save(out); print(m.size)

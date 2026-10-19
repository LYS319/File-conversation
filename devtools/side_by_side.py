"""한컴 PDF · 우리 PDF · 차이(겹침)를 한 장 그림으로: 눈으로 어디가 다른지 보는 용도. 컨테이너(pdftest:wp)에서:
    python side_by_side.py jobs.json 출력폴더 [쪽 수=3] [배율=0.9]
jobs.json: [{"id","oracle","nup","ours","rhwp"(선택)}]. 차이 그림: 검정=둘 다 글/선 있음, 빨강=한컴에만, 파랑=우리에만."""
import json, os, sys
import pymupdf
from PIL import Image, ImageChops


def render(doc, i, nup, s):
    """문서 쪽 i 를 회색 그림으로. nup=2 이면 한 장에 두 쪽 모아찍기를 반쪽씩 푼다(0.707배 되돌림)."""
    if nup == 1:
        if i >= len(doc): return None
        pm = doc[i].get_pixmap(matrix=pymupdf.Matrix(s, s), colorspace=pymupdf.csGRAY)
    else:
        if i // nup >= len(doc): return None
        pg = doc[i // nup]; w = pg.rect.width / nup; r = pymupdf.Rect(w * (i % nup), 0, w * (i % nup + 1), pg.rect.height)
        pm = pg.get_pixmap(matrix=pymupdf.Matrix(s / 0.7071, s / 0.7071), clip=r, colorspace=pymupdf.csGRAY)
    return Image.frombytes('L', (pm.width, pm.height), pm.samples)


def diff(h, o):
    size = (max(h.width, o.width), max(h.height, o.height))
    H = Image.new('L', size, 255); H.paste(h, (0, 0)); O = Image.new('L', size, 255); O.paste(o, (0, 0))
    mh, mo = H.point(lambda v: 255 if v < 170 else 0), O.point(lambda v: 255 if v < 170 else 0)
    out = Image.new('RGB', size, 'white')
    out.paste((255, 0, 0), mask=ImageChops.subtract(mh, mo)); out.paste((0, 0, 255), mask=ImageChops.subtract(mo, mh)); out.paste((40, 40, 40), mask=ImageChops.darker(mh, mo))
    return out


def main(jobs, outdir, npages=3, s=0.9):
    for j in jobs:
        d = os.path.join(outdir, j['id']); os.makedirs(d, exist_ok=True)
        ref, ours = pymupdf.open(j['oracle']), pymupdf.open(j['ours']); nup = j.get('nup', 1)
        rh = pymupdf.open(j['rhwp']) if j.get('rhwp') else None
        for i in range(npages):
            h, o = render(ref, i, nup, s), render(ours, i, 1, s)
            if h is None and o is None: break
            h = h or Image.new('L', o.size, 255); o = o or Image.new('L', h.size, 255)
            panels = [h.convert('RGB'), o.convert('RGB'), diff(h, o)]
            if rh is not None:
                r = render(rh, i, 1, s); panels.insert(2, (r or Image.new('L', h.size, 255)).convert('RGB'))
            W = sum(p.width for p in panels) + 8 * (len(panels) - 1); Hh = max(p.height for p in panels)
            canvas = Image.new('RGB', (W, Hh), (200, 200, 200)); x = 0
            for p in panels: canvas.paste(p, (x, 0)); x += p.width + 8
            canvas.save(os.path.join(d, f'비교_{i + 1}쪽.png'), optimize=True)
        print('완료', j['id'], flush=True)


if __name__ == '__main__':
    main(json.load(open(sys.argv[1], encoding='utf-8')), sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 3, float(sys.argv[4]) if len(sys.argv) > 4 else 0.9)

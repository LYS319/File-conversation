"""HWP 의 문단별 '저장된 줄 정보'(한컴이 저장할 때 계산한 줄 위치·높이)와 문단 모양을 한 줄씩 찍는다 — 한컴이 실제로 어떻게 놓았는지의 정답에 가장 가까운 자료.
    python diag_paras.py 문서.hwp [시작 문단] [개수]
열: 번호 | 문단모양 줄간격종류/값 위·아래간격 | 줄 수 · 첫 줄 위치(pt) · 줄 높이 · 글 높이 · 줄간격 | 다음 문단까지 저장된 거리 | 글자 수 | 컨트롤"""
import os, struct, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import hwp2html as H

H.load(sys.argv[1]); root = H.tree(H.records(H.dec(H.c.read('/BodyText/Section0'))))
paras = [n for n in root.ch if n.tag == 66]
a = int(sys.argv[2]) if len(sys.argv) > 2 else 0; k = int(sys.argv[3]) if len(sys.argv) > 3 else 60
def segs(n):
    L = []
    for s in (x for x in n.ch if x.tag == 69):
        for i in range(len(s.p) // 36):
            st, vp, lh, th, bl, sp, cs_, w_, tg = struct.unpack_from('<iiiiiiiiI', s.p, 36 * i); L.append((vp / 100, lh / 100, th / 100, sp / 100, tg))
    return L
for i in range(a, min(a + k, len(paras))):
    n = paras[i]; ps = H.parashapes[struct.unpack_from('<H', n.p, 8)[0]]; L = segs(n)
    txt = ''.join(v for ch in n.ch if ch.tag == 67 for _, v in H.para_text(ch.p) if isinstance(v, str)).strip()
    ct = [c.p[:4][::-1].decode('latin1') for c in n.ch if c.tag == 71]
    nxt = segs(paras[i + 1]) if i + 1 < len(paras) else None
    gap = f'{nxt[0][0] - L[0][0]:7.1f}' if nxt and L and nxt[0][0] > L[0][0] else '   ----'
    brk = ' 쪽나눔' if n.p[11] & 4 else ''
    print(f"{i:3d} ps(ls{ps['lstype']}/{ps['ls']} 위{ps['top']/200:g} 아래{ps['bottom']/200:g}) 줄{len(L)} y0={L[0][0] if L else -1:7.1f} lh={L[0][1] if L else 0:5.1f} th={L[0][2] if L else 0:5.1f} sp={L[0][3] if L else 0:5.1f} 다음까지{gap} 글{len(txt):3d} {ct}{brk}")

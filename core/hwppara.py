"""HWP5 문서에서 문단을 '글 + 글자 모양 + 문단 모양 + 한컴이 저장한 줄 정보'로 꺼낸다(V3 1단계 정답 데이터·줄 나눔 입력).
hwp2html 의 읽기 함수(load·records·tree·para_text)를 그대로 쓴다. 저장된 줄(PARA_LINE_SEG, 줄마다 36바이트): 글자 위치(chpos) @0, 세로 위치 @4, 줄 높이 @8, 글 높이 @12, 기준선 @16,
줄 간격 @20, 줄 시작 가로 위치 @24, 줄 폭 @28(HWPUNIT). 줄 폭이 줄마다 들어 있어 표 칸·글상자 속 문단도 칸 폭을 따로 계산하지 않고 쓸 수 있다.
    for p in iter_paragraphs('문서.hwp'): p.text, p.styles, p.shape, p.lines
"""
import bisect, struct, sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hwp2html as H

# 줄 폭에 영향이 없는 컨트롤(글자 폭을 차지하지 않거나 줄 밖에 있는 것): 구역·단 정의·머리말꼬리말 등. 이 밖의 컨트롤(표·그림·도형·수식 …)이 든 문단은 건너뛴다.
HARMLESS = {'secd', 'cold', 'pghd', 'pgnp', 'nwno', 'atno', 'head', 'foot', 'tcmt', 'bokm', 'idxm'}


@dataclass
class Para:
    text: str                 # 글자(탭은 '\t', 줄 바꿈은 '\n')
    pos: list                 # 글자마다 PARA_TEXT 안의 글자 위치(WCHAR 단위, chpos 와 같은 단위)
    sid: list                 # 글자마다 글자 모양 번호(H.charshapes 의 색인)
    shape: dict               # 문단 모양(H.parashapes 의 항목)
    lines: list               # 저장된 줄: [{'pos': chpos, 'x': 시작 가로 위치, 'w': 줄 폭, 'h': 줄 높이, 'y': 세로 위치}, …]
    ctrl: set = field(default_factory=set)      # 문단에 든 컨트롤 종류
    nest: int = 0             # 표·글상자 속 깊이(0 = 본문)
    index: int = 0            # 문서 안 순번
    sec: int = 0              # 구역 번호(쪽 정의가 구역마다 다르다)
    cols: int = 0             # 이 문단에 든 단 정의의 단 수(0 = 단 정의 없음; 이후 문단은 그 값을 이어받는다)


def _walk(nodes, nest, out):
    for n in nodes:
        if n.tag == 66: out.append((n, nest))
        _walk(n.ch, nest + (1 if n.tag == 71 else 0), out)


def iter_paragraphs(path, skip_ctrl=True):
    """문서 안 모든 문단(본문·표 칸·글상자). 저장된 줄이 없거나 글 위치를 못 맞추면 건너뛴다."""
    H.load(path)
    props = [struct.unpack_from('<I', pp, 0)[0] for t, _, pp in H.records(H.dec(H.c.read('/DocInfo'))) if t == 25]      # 문단 모양 속성 원값(비트 7 줄 나눔·비트 5~6 영어 줄 나눔·비트 9~15 공백 압축 …)
    secs = []
    while True:
        try: raw = H.c.read('/BodyText/Section%d' % len(secs))
        except KeyError: break
        secs.append(H.tree(H.records(H.dec(raw))))
    k = 0
    for si, root in enumerate(secs):
        found = []; _walk(root.ch, 0, found)
        for n, nest in found:
            text = H.para_text(next((c.p for c in n.ch if c.tag == 67), b''))
            csr = next(([struct.unpack_from('<II', c.p, 8 * i) for i in range(len(c.p) // 8)] for c in n.ch if c.tag == 68), [])
            segs = [c for c in n.ch if c.tag == 69]
            ctrl = {v[1] for _, v in text if isinstance(v, tuple)}
            lines = []
            for s in segs:
                for i in range(len(s.p) // 36):
                    pos, y, h, th, bl, sp, x, w, fl = struct.unpack_from('<IiiiiiiiI', s.p, 36 * i)
                    lines.append(dict(pos=pos, y=y, h=h, th=th, bl=bl, sp=sp, x=x, w=w, flags=fl))      # y 세로 위치, h 줄 높이, th 글자 높이, bl 기준선, sp 줄 간격(다음 줄까지 추가 간격)
            if not lines or not csr: continue
            if skip_ctrl and {c for c in ctrl - HARMLESS if not c.startswith('%')}: continue      # '%…' = 필드(하이퍼링크·누름틀 …) 시작 표시: 글자 폭이 없다
            chars = [(p, v) for p, v in text if isinstance(v, str)]
            starts = [a for a, _ in csr]
            sid = [csr[max(0, bisect.bisect_right(starts, p) - 1)][1] for p, _ in chars]
            psi = struct.unpack_from('<H', n.p, 8)[0]
            ps = dict(H.parashapes[psi], prop=props[psi] if psi < len(props) else 0)
            yield Para(''.join(v for _, v in chars), [p for p, _ in chars], sid, ps, lines, ctrl, nest, k, si, (H.cold_of(n) or (0,))[0])
            k += 1


if __name__ == '__main__':
    import collections
    for f in sys.argv[1:]:
        ps = list(iter_paragraphs(f)); multi = [p for p in ps if len(p.lines) >= 2]
        print(f, '문단', len(ps), '여러 줄', len(multi), '표·상자 속', sum(1 for p in multi if p.nest))
        for p in multi[:3]:
            print('  ', repr(p.text[:40]), '줄', [(l['pos'], l['x'], l['w']) for l in p.lines][:4], '문단 모양', {k: p.shape[k] for k in ('left', 'right', 'indent', 'align', 'bw')})

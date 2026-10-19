"""쪽 나눔 규칙 탐색(V3 2단계): 한컴이 저장한 줄(y·h·sp)과 문단 간격으로 쪽 나눔을 시뮬레이션해 저장된 쪽 시작(y 가 되돌아가는 줄)과 비교한다.
    PYTHONUTF8=1 python devtools/pagination_probe.py [--detail]
본문 문단(nest 0)만 쓴다: 표·그림이 든 문단의 줄 높이 h 에는 개체 높이가 들어 있어 그대로 쓰면 된다."""
import collections, glob, os, struct, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import hwppara as P
H = P.H
DETAIL = '--detail' in sys.argv


def page_body_h(path):
    """구역별 본문 높이(HWPUNIT) = 용지 높이 − 위 − 머리말 − 아래 − 꼬리말 (가로 용지는 폭과 바꿈)."""
    out = []; si = 0
    while True:
        try: raw = H.c.read('/BodyText/Section%d' % si)
        except KeyError: break
        root = H.tree(H.records(H.dec(raw))); pd = H.find(root, 73)
        if pd and len(pd.p) >= 40:
            pw, ph, pl, pr, pt, pb, phd, pft, pg = struct.unpack_from('<9I', pd.p, 0)
            if struct.unpack_from('<I', pd.p, 36)[0] & 1: pw, ph = ph, pw
            out.append(ph - pt - phd - pb - pft)
        else: out.append(None)
        si += 1
    return out


def main():
    tot = collections.Counter(); per_doc = []
    for f in sorted(glob.glob(str(ROOT / 'corpus' / 'rhwp*' / '**' / '*.hwp'), recursive=True)):
        if open(f, 'rb').read(8) != bytes.fromhex('d0cf11e0a1b11ae1') or os.path.getsize(f) > 6_000_000: continue
        try:
            ps = [p for p in P.iter_paragraphs(f, skip_ctrl=False) if p.nest == 0 and p.lines]; bh = page_body_h(f)
        except Exception: continue
        if not ps: continue
        c = collections.Counter(); prev = None; y = 0.0; first_on_page = True; last_end = None; prev_sec = 0
        ncol = 1
        for p in ps:
            Hb = bh[p.sec] if p.sec < len(bh) and bh[p.sec] else None
            if Hb is None: continue
            if p.cols: ncol = p.cols
            gap = ((prev.shape['bottom'] + p.shape['top']) / 2) if prev is not None and prev.sec == p.sec else 0
            if p.sec != prev_sec: y = 0.0; first_on_page = True
            prev_sec = p.sec
            for k, l in enumerate(p.lines):
                # 저장된 쪽 시작: 이 줄의 y 가 직전 줄의 y 이하
                stored_new = last_end is not None and l['y'] <= last_end[0] and not (k == 0 and p.sec != (prev.sec if prev else p.sec))
                cur = y + (gap if k == 0 else 0)
                # 시뮬레이션: 이 줄이 안 들어가면 새 쪽
                pbb = k == 0 and bool(p.shape['pbreak']) and not first_on_page      # 문단 앞에서 항상 쪽 나눔
                pred_new = (not first_on_page) and (cur + l['h'] > Hb or pbb)
                why = 'col' if ncol > 1 else ('pbb' if pbb else ('kwn' if prev is not None and k == 0 and (prev.shape['prop'] >> 17) & 1 else ('첫줄' if k == 0 else '문단중간')))
                c['줄'] += 1
                if stored_new: c['저장된 쪽 시작'] += 1
                if pred_new: c['예측 쪽 시작'] += 1
                if stored_new and pred_new: c['일치'] += 1
                elif stored_new: c['놓침:' + why] += 1
                if pred_new or stored_new:
                    y = 0.0; first_on_page = True
                    cur = 0.0
                # 쪽 맨 위 첫 문단의 위 간격은 저장된 y 를 따른다(시뮬레이션은 저장된 y 가 있으면 신뢰)
                y = cur + l['h'] + l['sp']; first_on_page = False
                last_end = (l['y'], l['h'])
            prev = p
        for k, v in c.items(): tot[k] += v
        per_doc.append((os.path.basename(f)[:34], c['저장된 쪽 시작'], c['예측 쪽 시작'], c['일치']))
    print('줄', tot['줄'], '| 저장된 쪽 시작', tot['저장된 쪽 시작'], '| 예측 쪽 시작', tot['예측 쪽 시작'], '| 일치', tot['일치'],
          '| 재현율 %.1f%% 정밀도 %.1f%%' % (100 * tot['일치'] / max(1, tot['저장된 쪽 시작']), 100 * tot['일치'] / max(1, tot['예측 쪽 시작'])))
    bad = sorted([d for d in per_doc if d[1] != d[3] or d[2] != d[3]], key=lambda d: -(abs(d[1] - d[3]) + abs(d[2] - d[3])))[:10]
    print('놓친 쪽 시작 원인:', {k: v for k, v in tot.items() if k.startswith('놓침')})
    print('어긋난 문서(저장 시작, 예측 시작, 일치):', bad)


if __name__ == '__main__': main()

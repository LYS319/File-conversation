"""세로 위치(vpos) 규칙 탐색(V3 2단계): 한컴이 저장한 줄 위치(PARA_LINE_SEG y·h·sp)로 줄 간격·문단 간격 규칙을 데이터로 확인한다.
    PYTHONUTF8=1 python devtools/vpos_probe.py
① 한 문단 안의 줄 피치(y 차이) = round4(줄 간격% × 줄 높이) 인지  ② 다음 문단 첫 줄 y − 이 문단 마지막 줄 끝(y+h+sp) = 아래 간격 + 위 간격 인지."""
import collections, glob, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import hwppara as P
H = P.H


def r4(v): return int(round(v / 4.0)) * 4


def main():
    in_ok = in_n = 0; bad_in = collections.Counter(); gaps = collections.Counter(); resid = collections.Counter(); ls_types = collections.Counter()
    for f in sorted(glob.glob(str(ROOT / 'corpus' / 'rhwp*' / '**' / '*.hwp'), recursive=True)):
        if open(f, 'rb').read(8) != bytes.fromhex('d0cf11e0a1b11ae1') or os.path.getsize(f) > 6_000_000: continue
        try: ps = list(P.iter_paragraphs(f, skip_ctrl=False))
        except Exception: continue
        prev = None
        for p in ps:
            if p.nest != 0: prev = None; continue
            ls, lt = p.shape['ls'], p.shape['lstype']; ls_types[lt] += 1
            L = p.lines
            for a, b in zip(L, L[1:]):
                if b['y'] <= a['y']: continue      # 쪽·단 넘김
                dy = b['y'] - a['y']; in_n += 1
                pred = r4(ls / 100 * a['h']) if lt == 0 else None
                if pred is not None:
                    if abs(dy - pred) <= 4: in_ok += 1
                    else: bad_in[(lt, ls, a['h'], dy)] += 1
            if prev is not None and L and prev.lines and not (p.ctrl - P.HARMLESS) and not (prev.ctrl - P.HARMLESS):
                pl = prev.lines[-1]; gap = L[0]['y'] - (pl['y'] + pl['h'] + pl['sp'])
                if L[0]['y'] > pl['y']:
                    exp = prev.shape['bottom'] + p.shape['top']
                    resid[gap - exp] += 1
                    if gap - exp != 0: gaps[(prev.shape['bottom'], p.shape['top'], gap)] += 1
            prev = p
    print('① 줄 피치(percent 줄 간격) 일치 %d / %d (%.1f%%)' % (in_ok, in_n, 100 * in_ok / max(1, in_n)), '| 줄 간격 종류 분포', dict(ls_types))
    print('   어긋난 예', bad_in.most_common(6))
    tot = sum(resid.values()); print('② 문단 사이 간격 − (아래 간격 + 위 간격) 분포(0 이면 일치):', resid.most_common(8), '/ 전체', tot)
    print('   어긋난 (아래, 위, 실제 간격) 예', gaps.most_common(8))


if __name__ == '__main__': main()

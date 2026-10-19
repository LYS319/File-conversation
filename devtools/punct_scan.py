"""문장부호 폭 점검 대상 고르기: 코퍼스에서 (글꼴, 문장부호) 쌍의 쓰임 횟수를 세고, 폭표 값이 0 이거나 다른 글꼴들의 중앙값과 크게 다른(= 글리프 없음 대체값 의심) 쌍을 많이 쓰인 순으로 보인다.
    PYTHONUTF8=1 python devtools/punct_scan.py [상위 개수=40]
→ 이 쌍들을 합성 사다리로 한컴에서 실측한다(synth_ladder.py build --faces … --units …)."""
import collections, glob, os, statistics as st, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'devtools')); sys.path.insert(0, str(ROOT))
import linebreak_eval as L
M, P, H = L.M, L.P, L.H
CHARS = "·•…~-–—'\"‘’“”()[]{}/%;:,.!?*&@#+=<>※"
TOP = int(sys.argv[1]) if len(sys.argv) > 1 else 40


def main():
    fs = M._load(); faces = sorted(fs)
    med = {c: st.median(M.advance(f, c) for f in faces) for c in CHARS}
    use = collections.Counter()
    for f in sorted(glob.glob(str(ROOT / 'corpus' / 'rhwp*' / '**' / '*.hwp'), recursive=True)):
        if open(f, 'rb').read(8) != L.OLE or os.path.getsize(f) > 8_000_000: continue
        try: ps = list(P.iter_paragraphs(f))
        except Exception: continue
        for p in ps:
            cs = [H.charshapes[k] for k in p.sid]
            for c, s, l in zip(p.text, cs, L.slots(p.text)):
                if c in CHARS: use[(s['langs'][l]['face'], c)] += 1
    rows = []
    for (face, c), n in use.items():
        w = M.advance(face, c)
        if w == 0 or abs(w - med[c]) > 0.3: rows.append((n, face, c, round(w, 2), round(med[c], 2), M.find(face) is not None))
    rows.sort(reverse=True)
    print('쓰임 총 %d / 이상 의심 쌍 %d (쓰임 합 %d)' % (sum(use.values()), len(rows), sum(r[0] for r in rows)))
    for n, face, c, w, m, has in rows[:TOP]: print('%6d  %-14s %s  표 %.2f  중앙값 %.2f  %s' % (n, face, c, w, m, '' if has else '(표에 글꼴 없음)'))


if __name__ == '__main__': main()

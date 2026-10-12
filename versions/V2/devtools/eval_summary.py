"""세 세트(사용자 8·공개 20·공개 108) 평가 결과를 기준선(gates.json)과 비교해 한 줄씩 ✓/✗ 로 찍는다.
프로젝트 루트에서:  python versions/V2/devtools/eval_summary.py [꼬리표] [--before 꼬리표]
  꼬리표 없음      corpus/_eval/user · rhwp · rhwp2          (run_eval.sh 를 꼬리표 없이 돌린 결과)
  꼬리표 x         corpus/_eval/user_x · rhwp_x · rhwp2_x    (EVAL_TAG=x 로 돌린 결과)
  --before 꼬리표  기준을 못 넘은 세트는 그 꼬리표 결과(없으면 '')와 문서별 차이(evaldiff.py)를 이어서 보여 준다
기준을 못 넘기면 종료 코드 1. 기준선은 gates.json 한 곳에서만 고친다."""
import json, os, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EVAL = ROOT / 'corpus' / '_eval'


def read_total(folder):
    """eval.txt 의 '전체:' 줄에서 지표를 뽑는다. 없으면 None."""
    f = folder / 'eval.txt'
    if not f.is_file(): return None
    line = next((l for l in f.read_text(encoding='utf-8').splitlines() if l.startswith('전체:')), None)
    if not line: return None
    num = lambda pat: float(re.search(pat, line).group(1)) if re.search(pat, line) else None
    return dict(n=num(r'(\d+)건'), match=num(r'쪽 수 같음 (\d+)'), diff=num(r'차이 합계 (\d+)'), recall=num(r'글재현 ([\d.]+)'),
                dy=num(r'dy 중앙값의 평균 ([\d.]+)'), sim=num(r'유사도 ([\d.]+)'))


def main(argv):
    tag = ''; before = None; i = 0
    while i < len(argv):
        if argv[i] == '--before': before = argv[i + 1] if i + 1 < len(argv) else ''; i += 2
        else: tag = argv[i]; i += 1
    gates = json.loads((HERE / 'gates.json').read_text(encoding='utf-8'))
    sfx = f'_{tag}' if tag else ''
    bad = []
    print(f'회귀 관문 — corpus/_eval/*{sfx}  (기준선 갱신: {gates["_갱신"]})')
    for key in ('user', 'rhwp', 'rhwp2'):
        g = gates[key]; t = read_total(EVAL / f'{key}{sfx}')
        if t is None: print(f'  ? {g["이름"]}: 결과 없음 (corpus/_eval/{key}{sfx}/eval.txt)'); bad.append(key); continue
        checks = [('쪽 일치', t['match'], g['쪽_일치_최소'], t['match'] >= g['쪽_일치_최소']),
                  ('쪽 오차 합', t['diff'], g['차이_합계_최대'], t['diff'] <= g['차이_합계_최대']),
                  ('유사도', t['sim'], g['유사도_최소'], t['sim'] >= g['유사도_최소'] - 1e-9),
                  ('dy', t['dy'], g['dy_최대'], t['dy'] <= g['dy_최대'])]
        ok = all(c[3] for c in checks)
        print(f'  {"✓" if ok else "✗"} {g["이름"]:<18} 쪽 {t["match"]:.0f}/{t["n"]:.0f}(≥{g["쪽_일치_최소"]}) · 오차 합 {t["diff"]:.0f}(≤{g["차이_합계_최대"]}) · 유사도 {t["sim"]}(≥{g["유사도_최소"]}) · dy {t["dy"]}(≤{g["dy_최대"]})')
        for name, val, lim, good in checks:
            if not good: print(f'      ✗ {name}: {val} (기준 {lim})')
        if not ok: bad.append(key)
    if bad and before is not None:
        env = dict(os.environ, PYTHONUTF8='1')
        for key in bad:
            a, b = EVAL / f'{key}{"_" + before if before else ""}', EVAL / f'{key}{sfx}'
            if a.is_dir() and b.is_dir() and a != b:
                print(f'\n— {key}: 문서별 차이 ({a.name} → {b.name})')
                subprocess.run([sys.executable, str(HERE / 'evaldiff.py'), str(a), str(b)], env=env)
    print('\n결과:', '모두 통과' if not bad else '기준 미달: ' + ', '.join(bad))
    return 1 if bad else 0


if __name__ == '__main__':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    sys.exit(main(sys.argv[1:]))

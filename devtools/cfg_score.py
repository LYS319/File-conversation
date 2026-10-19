"""설정 후보를 '한컴 저장 위치와의 일치 점수'로 고를 수 있는지 검증한다(정답 PDF 없이 파일 하나로 판단할 수 있는지).
같은 문서를 설정만 바꿔 돌린 평가 폴더들(VPOS_SCORE=1 로 돌려 PDF 옆에 .score.json 이 있는 것)을 읽어, 문서마다
  점수가 가장 좋은 설정을 골랐을 때의 실제 유사도(한컴 PDF 대비)를 기본 설정·정답 선택(최선)과 비교한다.
    python devtools/cfg_score.py 기본태그 후보태그 [후보태그...]      예) sc_def sc_sm100 sc_sl6
점수 = 한컴 쪽(저장 위치가 30pt 넘게 거꾸로 갈 때마다 +1)과 우리 쪽이 다른 문단 비율 + 쪽 수 차이 항 + (같은 쪽 문단의) 위치 오차 항."""
import json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / 'corpus' / '_eval'
DROP = 30.0; FIRST_MAX = 150.0


def stats(sc):
    ms = sc['ms']; n = len(ms)
    if n < 10: return None
    hp = 0; mis = 0; err = []; prev = None
    for pi, page, end, rel, vp in ms:
        if prev is not None and prev - vp > DROP and vp <= FIRST_MAX: hp += 1
        prev = vp
        if page != hp: mis += 1
        else: err.append(min(abs(rel - vp), 30.0))
    return dict(n=n, pages=sc['pages'], hp=hp + 1, mis=mis / n, err=(sum(err) / len(err)) if err else 30.0)


FORMULAS = {
    '쪽 수 차이': lambda s: abs(s['pages'] - s['hp']),
    '쪽 다른 문단 비율': lambda s: s['mis'],
    '위치 오차': lambda s: s['err'] / 30,
    '합(쪽차+배정+위치)': lambda s: abs(s['pages'] - s['hp']) / max(s['hp'], 1) * 3 + s['mis'] + s['err'] / 30,
}


def load(sname, tag):
    f = EVAL / f'{sname}_{tag}'
    if not (f / 'eval.json').is_file(): return {}
    ev = json.loads((f / 'eval.json').read_text(encoding='utf-8')); out = {}
    for i, r in enumerate(ev):
        if 'fail' in r or r.get('suspect') or 'ink' not in r: continue
        sc = next((f / x for x in os.listdir(f) if x.startswith(f'{i:03d}_') and x.endswith('.score.json')), None)
        st = stats(json.loads(sc.read_text(encoding='utf-8'))) if sc else None
        out[r['doc']] = dict(ink=r['ink'], ok=(r['ours'] == r['ref']), pages=r['ours'], ref=r['ref'], st=st)
    return out


def main(tags, tol=0.01):
    base, cands = tags[0], tags
    print('후보 설정:', ', '.join(tags), '(첫째가 기본)')
    for name, fm in FORMULAS.items():
        tot = dict(docs=0, differ=0, def_ink=0.0, sel_ink=0.0, best_ink=0.0, helped=0, hurt=0, nosc=0, picked_other=0)
        worst = []
        for sname in ('user', 'rhwp', 'rhwp2'):
            data = [load(sname, t) for t in tags]
            for doc in data[0]:
                rows = [d.get(doc) for d in data]
                if any(r is None for r in rows): continue
                tot['docs'] += 1
                inks = [r['ink'] for r in rows]; pages = [r['pages'] for r in rows]
                if max(inks) - min(inks) <= tol and len(set(pages)) == 1: tot['def_ink'] += inks[0]; tot['sel_ink'] += inks[0]; tot['best_ink'] += max(inks); continue      # 설정이 결과를 안 바꾼 문서
                tot['differ'] += 1
                sts = [r['st'] for r in rows]
                if any(s is None for s in sts): pick = 0; tot['nosc'] += 1      # 점수를 못 매기면 기본
                else:
                    sc = [fm(s) for s in sts]; pick = min(range(len(sc)), key=lambda k: (sc[k], k))      # 동점은 기본(앞선) 설정
                tot['def_ink'] += inks[0]; tot['sel_ink'] += inks[pick]; tot['best_ink'] += max(inks)
                if pick: tot['picked_other'] += 1
                d = inks[pick] - inks[0]
                if d > tol: tot['helped'] += 1
                elif d < -tol: tot['hurt'] += 1; worst.append((d, sname, doc, tags[pick]))
        n = tot['docs']
        print('\n[점수식: %s] 문서 %d건 중 설정에 따라 결과가 달라진 문서 %d건(점수 없음 %d) — 기본 외 설정을 고른 문서 %d, 좋아짐 %d, 나빠짐 %d' % (name, n, tot['differ'], tot['nosc'], tot['picked_other'], tot['helped'], tot['hurt']))
        print('   평균 유사도: 기본 %.4f → 점수로 고름 %.4f (정답 선택 시 상한 %.4f)' % (tot['def_ink'] / n, tot['sel_ink'] / n, tot['best_ink'] / n))
        for d, s, doc, t in sorted(worst)[:5]: print('   나빠짐 %+.3f  %s/%s  → %s' % (d, s, doc[:50], t))


if __name__ == '__main__':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    main(sys.argv[1:])

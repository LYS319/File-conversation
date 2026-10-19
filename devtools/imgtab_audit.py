"""그림·표 배치 점검: 한컴 PDF 와 우리 PDF 를 나란히 놓고 (1) 그림이 같은 자리에 있는지 (2) 표 선(칸 경계)이 같은 자리에 있는지를 문서별로 센다.
쪽 수가 같은 문서만 쪽 단위로 맞춰 본다(쪽 수가 다르면 쪽이 밀려 어긋남이 뒤섞이니 따로 표시). nup(한 장에 두 쪽) 문서는 제외.
    python devtools/imgtab_audit.py <평가 꼬리표> [세트...]      세트: user rhwp rhwp2 (기본 셋 다)   예) fin14
    결과: corpus/_eval/imgtab_<꼬리표>.md
그림 = PDF 에 들어간 이미지의 상자. 한컴 그림마다 우리 쪽에서 크기가 비슷하고(가로·세로 0.7~1.4 배) 중심이 25pt 안인 그림을 짝지어, 짝 없는 한컴 그림 = 빠진 그림, 짝 없는 우리 그림 = 엉뚱한 곳/덤 그림.
표 선 = 쪽 안 가는 사각형·선(세로: 폭<2.5·높이>12, 가로: 높이<2.5·폭>12)을 이어 붙인 것. 한컴 선마다 같은 방향·수직 좌표 차 3pt(느슨하게 8pt) 안·길이 절반 이상 겹치는 우리 선이 있으면 맞음."""
import json, sys, os
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / 'corpus' / '_eval'
SETS = {'rhwp': (ROOT / 'corpus' / 'rhwp', ROOT / 'corpus' / 'rhwp' / 'manifest.json'),
        'rhwp2': (ROOT / 'corpus' / 'rhwp2', ROOT / 'corpus' / 'rhwp2' / 'manifest.json'),
        'user': (ROOT / 'corpus', ROOT / 'corpus' / 'user_manifest.json')}


def images(page):
    out = []
    for im in page.get_image_info():
        x0, y0, x1, y1 = im['bbox']
        if x1 - x0 < 20 or y1 - y0 < 20: continue      # 20pt 미만은 그림으로 안 센다: 한컴 PDF 는 글리프(16×19pt 남짓 비트맵)를 그림으로 내고, 우리 PDF 는 테두리 조각을 가는 그림으로 낸다
        if (x1 - x0) * (y1 - y0) > 0.85 * page.rect.width * page.rect.height: continue      # 쪽 전체 바탕 그림은 안 센다(한컴은 바탕을 그림으로 안 내는 일이 많다)
        out.append((x0, y0, x1, y1))
    return out


def lines(page):
    """({세로 선}, {가로 선}) = 각각 [(수직 좌표, 시작, 끝)] 를 이어 붙인 것."""
    v, h = [], []
    for d in page.get_drawings():
        r = d['rect']
        if r.width < 2.5 and r.height > 12: v.append(((r.x0 + r.x1) / 2, r.y0, r.y1))
        elif r.height < 2.5 and r.width > 12: h.append(((r.y0 + r.y1) / 2, r.x0, r.x1))
    def merge(segs):
        segs = sorted((round(c * 2) / 2, a, b) for c, a, b in segs); out = []
        for c, a, b in segs:
            if out and abs(out[-1][0] - c) < 0.6 and a <= out[-1][2] + 1.5: out[-1] = (out[-1][0], out[-1][1], max(out[-1][2], b))
            else: out.append((c, a, b))
        return out
    def unhatch(segs):      # 가는 빗금 무늬(2pt 간격 선이 수십 개)는 표 선이 아니다: 양옆 5pt 안에 선이 5개 이상이면 뺀다
        xs = sorted(c for c, a, b in segs)
        return [t for t in segs if sum(1 for x in xs if abs(x - t[0]) <= 5) < 5]
    return unhatch(merge(v)), unhatch(merge(h))


def match_images(ref, ours):
    pairs = []
    for i, (a0, b0, a1, b1) in enumerate(ref):
        for j, (c0, d0, c1, d1) in enumerate(ours):
            wr, hr = (c1 - c0) / max(a1 - a0, 1), (d1 - d0) / max(b1 - b0, 1)
            dist = (((a0 + a1) - (c0 + c1)) ** 2 / 4 + ((b0 + b1) - (d0 + d1)) ** 2 / 4) ** .5
            if 0.7 <= wr <= 1.4 and 0.7 <= hr <= 1.4 and dist <= 25: pairs.append((dist, i, j))
    pairs.sort(); ui, uj, offs = set(), set(), []
    for dist, i, j in pairs:
        if i in ui or j in uj: continue
        ui.add(i); uj.add(j); offs.append(dist)
    return len(ui), len(ref) - len(ui), len(ours) - len(uj), offs


def match_lines(ref, ours, tol):
    hit = 0
    for c, a, b in ref:
        for c2, a2, b2 in ours:
            ov = min(b, b2) - max(a, a2)
            if abs(c - c2) <= tol and ov >= 0.5 * min(b - a, b2 - a2): hit += 1; break
    return hit


def main(tag, sets):
    out = [f'# 그림·표 배치 점검 — {tag}', '', '쪽 수가 같은 문서만 쪽 단위로 비교(nup·정답 의심 문서 제외). 그림: 한컴 그림 중 우리 쪽에 같은 크기·25pt 안 짝이 있는 비율(짝 못 찾음 = 빠졌거나 다른 곳). 표 선: 한컴 선 중 우리 선과 3pt 안 겹친 비율.', '']
    tot = dict(ri=0, mi=0, mis=0, ex=0, lv=0, lvh=0, lvh8=0, lh=0, lhh=0, lhh8=0, docs=0)
    for sname in sets:
        base, man_path = SETS[sname]; folder = EVAL / f'{sname}_{tag}'
        if not (folder / 'eval.json').is_file(): out.append(f'(결과 없음: {folder})'); continue
        ev = json.loads((folder / 'eval.json').read_text(encoding='utf-8'))
        man = [m for m in json.loads(man_path.read_text(encoding='utf-8')) if 'oracle_pdf' in m]
        rows = []; skipped = []
        for i, m in enumerate(man):
            name = m['path']; r = ev[i] if i < len(ev) else {}
            if r.get('suspect') or 'fail' in r or m.get('nup', 1) != 1: skipped.append(name + (' (nup)' if m.get('nup', 1) != 1 else '')); continue
            ours_f = next((f for f in os.listdir(folder) if f.startswith(f'{i:03d}_') and f.endswith('.pdf')), None)
            if not ours_f: continue
            ref_p = (base / m['oracle_pdf']) if not str(m['oracle_pdf']).startswith('/') else Path(m['oracle_pdf'])
            try: R = pymupdf.open(str(ref_p)); O = pymupdf.open(str(folder / ours_f))
            except Exception: continue
            if len(R) != len(O): skipped.append(f'{name} (쪽 {len(O)}/{len(R)})'); continue
            ri = mi = mis = ex = lv = lvh = lvh8 = lh = lhh = lhh8 = 0; offs = []
            for pr, po in zip(R, O):
                ir, io = images(pr), images(po)
                a, b, c, o = match_images(ir, io); ri += len(ir); mi += a; mis += b; ex += c; offs += o
                (vr, hr_), (vo, ho) = lines(pr), lines(po)
                lv += len(vr); lvh += match_lines(vr, vo, 3); lvh8 += match_lines(vr, vo, 8)
                lh += len(hr_); lhh += match_lines(hr_, ho, 3); lhh8 += match_lines(hr_, ho, 8)
            rows.append((name, len(R), ri, mi, mis, ex, (sum(offs) / len(offs)) if offs else 0, lv, lvh, lvh8, lh, lhh, lhh8))
            for k, v in zip(('ri', 'mi', 'mis', 'ex', 'lv', 'lvh', 'lvh8', 'lh', 'lhh', 'lhh8'), (ri, mi, mis, ex, lv, lvh, lvh8, lh, lhh, lhh8)): tot[k] += v
            tot['docs'] += 1
        out += [f'## {sname} — 비교한 문서 {len(rows)}건, 제외 {len(skipped)}건', '',
                '| 문서 | 쪽 | 한컴 그림 | 짝 찾음 | 빠짐 | 덤 | 짝 평균 오차pt | 세로선 한컴 | 맞음3pt | 맞음8pt | 가로선 한컴 | 맞음3pt | 맞음8pt |', '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
        for r in sorted(rows, key=lambda r: -(r[4] + r[5] + (r[7] - r[9]) * .1 + (r[10] - r[12]) * .1)):
            if r[2] == 0 and r[5] == 0 and r[7] + r[10] == 0: continue      # 그림도 선도 없는 문서는 줄이 길어지니 뺀다
            out.append('| %s | %d | %d | %d | %d | %d | %.1f | %d | %d | %d | %d | %d | %d |' % r)
        if skipped: out += ['', '제외: ' + ', '.join(skipped[:40]) + (' …' if len(skipped) > 40 else '')]
        out.append('')
    pct = lambda a, b: '%.1f%%' % (100 * a / b) if b else '-'
    out[3:3] = ['**합계 (쪽 수 같은 %d건)**: 한컴 그림 %d → 짝 찾음 %s(빠짐 %d, 덤 %d) · 세로선 %d → 3pt 안 %s / 8pt 안 %s · 가로선 %d → 3pt 안 %s / 8pt 안 %s' % (
        tot['docs'], tot['ri'], pct(tot['mi'], tot['ri']), tot['mis'], tot['ex'], tot['lv'], pct(tot['lvh'], tot['lv']), pct(tot['lvh8'], tot['lv']), tot['lh'], pct(tot['lhh'], tot['lh']), pct(tot['lhh8'], tot['lh'])), '']
    dst = EVAL / f'imgtab_{tag}.md'; dst.write_text('\n'.join(out), encoding='utf-8'); print('\n'.join(out[:6])); print('->', dst)


if __name__ == '__main__':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except Exception: pass
    main(sys.argv[1], sys.argv[2:] or ['user', 'rhwp', 'rhwp2'])

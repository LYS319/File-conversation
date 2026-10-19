"""HWP -> HWPX 엔진 3종 비교: 우리(HWP_CLI=off 자체 변환) · hwp-cli convert · rhwp export-hwpx.
같은 렌더러(hwp-cli render)로 세 HWPX 를 그려 한컴 정답 PDF 와 eval_layout 지표로 비교하고, hwp-cli validate 로 형식 유효성도 본다.
    python devtools/hwpx_compare.py [--max-mb 10]      (프로젝트 루트에서, 윈도 호스트. 필요: tools/hwp-cli/hwp.exe, tools/rhwp/rhwp, 도커 pdftest:wp)
출력: corpus/_eval/hwpx_cmp/{ours,cli,rhwp}/eval.txt, summary.txt
주의: 렌더러가 hwp-cli 라서 hwp-cli 가 자기 HWPX 를 더 잘 읽는 편향이 있을 수 있다(한컴 한글에서 직접 열어 본 확인은 별개).
사용자 문서(samples/)도 포함하지만 모두 로컬 처리다(외부 전송 없음)."""
import json, os, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HWP = ROOT / 'tools' / 'hwp-cli' / 'hwp.exe'
CONV = ROOT / 'convert.py'
OUT = ROOT / 'corpus' / '_eval' / 'hwpx_cmp'
ENGINES = ('ours', 'cli', 'rhwp')


def docs(max_mb):
    rows = []
    for m in json.loads((ROOT / 'corpus' / 'user_manifest.json').read_text(encoding='utf-8')):
        name = m['path'].split('/')[-1]
        if name.lower().endswith('.hwp'): rows.append(dict(src=ROOT / 'samples' / name, csrc='/samples/' + name, oracle='/c/' + m['oracle_pdf'], nup=m.get('nup', 1)))
    for m in json.loads((ROOT / 'corpus' / 'rhwp' / 'manifest.json').read_text(encoding='utf-8')):
        if m['path'].lower().endswith('.hwp') and 'oracle_pdf' in m:
            rows.append(dict(src=ROOT / 'corpus' / 'rhwp' / m['path'], csrc='/c/rhwp/' + m['path'], oracle='/c/rhwp/' + m['oracle_pdf'], nup=1))
    return [r for r in rows if r['src'].exists() and r['src'].stat().st_size <= max_mb * 1e6]


def run(cmd, cwd=None, timeout=400, env=None):
    t = time.time()
    try: r = subprocess.run(cmd, capture_output=True, cwd=cwd, timeout=timeout, env=env)
    except subprocess.TimeoutExpired: return 124, time.time() - t
    return r.returncode, time.time() - t


def main():
    max_mb = float(sys.argv[sys.argv.index('--max-mb') + 1]) if '--max-mb' in sys.argv else 10
    ds = docs(max_mb); print(len(ds), '문서', flush=True)
    work = OUT / 'work'; shutil.rmtree(OUT, ignore_errors=True)
    for e in ENGINES: (OUT / 'hwpx' / e).mkdir(parents=True); (OUT / 'pdf' / e).mkdir(parents=True)
    work.mkdir(parents=True)
    times = {e: {} for e in ENGINES}
    # 1) 변환
    for i, d in enumerate(ds):
        sn = f'{i:03d}'
        rc, t = run([sys.executable, str(CONV), str(d['src']), str(OUT / 'hwpx' / 'ours' / f'{sn}.hwpx')], env={**os.environ, 'HWP_CLI': 'off', 'PYTHONIOENCODING': 'utf-8'}); times['ours'][sn] = (rc, t)
        tmp = work / 'c'; shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir()
        rc, t = run([str(HWP), 'convert', str(d['src']), '-o', 'o.hwpx'], cwd=tmp); times['cli'][sn] = (rc, t)
        if (tmp / 'o.hwpx').exists(): shutil.move(str(tmp / 'o.hwpx'), OUT / 'hwpx' / 'cli' / f'{sn}.hwpx')
        print('변환', sn, d['src'].name[:30], flush=True)
    jobs = [dict(i=i, src=d['csrc']) for i, d in enumerate(ds)]
    (OUT / 'jobs.json').write_text(json.dumps(jobs), encoding='utf-8')
    script = ("import json,subprocess,time,sys\n"
              "J=json.load(open('/o/jobs.json'));R={}\n"
              "for j in J:\n"
              "    sn='%03d'%j['i'];t=time.time()\n"
              "    try: r=subprocess.run(['/x/rhwp','export-hwpx',j['src'],'/o/hwpx/rhwp/'+sn+'.hwpx'],capture_output=True,timeout=400);rc=r.returncode\n"
              "    except subprocess.TimeoutExpired: rc=124\n"
              "    R[sn]=(rc,time.time()-t)\n"
              "json.dump(R,open('/o/rhwp_times.json','w'))\n")
    (OUT / 'rhwp_batch.py').write_text(script, encoding='utf-8')
    subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--read-only', '--tmpfs', '/tmp:size=1g', '--tmpfs', '/x:size=100m,exec', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--memory', '4g',
                    '-v', f'{ROOT / "tools" / "rhwp"}:/t:ro', '-v', f'{ROOT / "corpus"}:/c:ro', '-v', f'{ROOT / "samples"}:/samples:ro', '-v', f'{OUT}:/o', 'pdftest:wp',
                    'sh', '-c', 'cp /t/rhwp /x/rhwp && chmod +x /x/rhwp && python /o/rhwp_batch.py'], env={**os.environ, 'MSYS_NO_PATHCONV': '1'})
    for sn, v in json.loads((OUT / 'rhwp_times.json').read_text()).items(): times['rhwp'][sn] = tuple(v)
    # 2) 검증 + 렌더
    res = {e: [] for e in ENGINES}; valid = {e: [0, 0] for e in ENGINES}; made = {e: 0 for e in ENGINES}
    for i, d in enumerate(ds):
        sn = f'{i:03d}'
        for e in ENGINES:
            hx = OUT / 'hwpx' / e / f'{sn}.hwpx'
            if not hx.exists() or hx.stat().st_size == 0: continue
            made[e] += 1
            tmp = work / 'r'; shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir(); shutil.copy(hx, tmp / 'x.hwpx')
            rc, _ = run([str(HWP), 'validate', 'x.hwpx'], cwd=tmp, timeout=120); valid[e][0 if rc == 0 else 1] += 1
            rc, _ = run([str(HWP), 'render', 'x.hwpx', '-o', 't.pdf'], cwd=tmp, timeout=400)
            if rc == 0 and (tmp / 't.pdf').exists():
                res[e].append(dict(path=d['csrc'], oracle_pdf=d['oracle'], nup=d['nup'])); k = len(res[e]) - 1
                shutil.move(str(tmp / 't.pdf'), OUT / 'pdf' / e / f'{k:03d}_{Path(d["csrc"]).stem[:40]}.pdf')
        print('렌더', sn, flush=True)
    # 3) 지표(도커, eval_layout --reuse: 이미 있는 PDF 는 변환하지 않고 지표만)
    lines = []
    for e in ENGINES:
        (OUT / 'pdf' / e / 'manifest.json').write_text(json.dumps(res[e], ensure_ascii=False), encoding='utf-8')
        r = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--read-only', '--tmpfs', '/tmp:size=1g', '--cap-drop', 'ALL', '--memory', '4g',
                            '-v', f'{ROOT}:/work:ro', '-v', f'{ROOT / "corpus"}:/c:ro', '-v', f'{ROOT / "samples"}:/samples:ro', '-v', f'{OUT / "pdf" / e}:/out', 'pdftest:wp',
                            'python', '-W', 'ignore', '/work/devtools/eval_layout.py', '/c', '/out/manifest.json', '/out', '--reuse'], capture_output=True, text=True, encoding='utf-8', env={**os.environ, 'MSYS_NO_PATHCONV': '1'})
        tail = [l for l in r.stdout.splitlines() if l.startswith('전체')]
        n_ok = sum(1 for v in times[e].values() if v[0] == 0)
        tsum = sum(v[1] for v in times[e].values())
        lines.append(f'{e}: 문서 {len(ds)} · 변환 성공 {n_ok} · HWPX 생성 {made[e]} · validate 통과 {valid[e][0]}/{valid[e][0] + valid[e][1]} · 렌더 성공 {len(res[e])} · 변환 시간 합 {tsum:.0f}초')
        lines.append('   ' + (tail[0] if tail else r.stderr[-300:]))
    (OUT / 'summary.txt').write_text('\n'.join(lines), encoding='utf-8'); print('\n'.join(lines))


if __name__ == '__main__':
    main()

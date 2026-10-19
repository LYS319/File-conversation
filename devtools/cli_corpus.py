"""hwp-cli(윈도 호스트)로 평가 세트(rhwp|rhwp2|user)의 문서를 PDF 로 바꿔 corpus/_eval/<세트>_cli/ 에 eval_layout 이름(NNN_이름.pdf)으로 저장하고, 문서별 시간·실패를 times.json 에 적는다.
    PYTHONUTF8=1 python devtools/cli_corpus.py rhwp2
쪽 수·유사도 측정은 run_engine3.sh 가 eval_layout.py --engine none 으로 한다(세 엔진을 같은 지표로)."""
import json, shutil, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / 'tools' / 'hwp-cli' / 'hwp.exe'


def main(s):
    base = ROOT / 'corpus' / ('rhwp' if s == 'rhwp' else 'rhwp2' if s == 'rhwp2' else '')
    man = [m for m in json.loads((ROOT / 'corpus' / ('user_manifest.json' if s == 'user' else s + '/manifest.json')).read_text(encoding='utf-8')) if 'oracle_pdf' in m]
    out = ROOT / 'corpus' / '_eval' / (s + '_cli'); out.mkdir(parents=True, exist_ok=True); work = Path(tempfile.mkdtemp()); times = {}
    for i, m in enumerate(man):
        src0 = ROOT / m['path'].lstrip('/') if m['path'].startswith('/') else base / m['path']
        src = work / ('in' + src0.suffix); dst = work / 'out.pdf'; shutil.copyfile(src0, src); dst.unlink(missing_ok=True)      # 윈도 폴더 바인드 읽기 지연을 시간에서 뺀다
        t = time.time(); err = ''
        try:
            r = subprocess.run([str(EXE), 'render', '--format', 'pdf', '-o', str(dst), str(src)], capture_output=True, timeout=600)
            if r.returncode: err = ((r.stderr or r.stdout).decode('utf-8', 'replace').strip().splitlines() or ['exit %d' % r.returncode])[-1][:80]
        except subprocess.TimeoutExpired: err = '시간 초과 600s'
        secs = round(time.time() - t, 1)
        if dst.exists() and dst.stat().st_size and not err: shutil.copyfile(dst, out / ('%03d_%s.pdf' % (i, Path(m['path']).stem[:40])))
        elif not err: err = '빈 PDF'
        times[m['path']] = dict(sec=secs, err=err); src.unlink(missing_ok=True); print(s, i, m['path'][-40:], secs, err, flush=True)
        (out / 'times.json').write_text(json.dumps(times, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__': main(sys.argv[1])

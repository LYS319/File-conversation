"""HWP -> HWPX 변환 엔진 비교: 우리 변환기(HWP_CLI=off) 대 hwp-cli 직접 변환을, 같은 렌더러(hwp-cli)로 그려 한컴 정답 PDF 와 비교한다.
    python devtools/engine_compare.py        (프로젝트 루트에서. 필요: tools/hwp-cli/hwp.exe, 도커 이미지 pdftest:wp, corpus/rhwp/)
출력: corpus/_dev_out/engine_compare/result.txt  (문서별 쪽 수·모양 유사도, 평균, 쪽 수 일치 수)
유사도는 쪽을 40x56 칸으로 나눠 칸마다 먹 농도를 겹쳐 보는 거친 지표라 방향만 참고한다. hwp-cli 윈도 빌드는 출력 이름이 약 28자를 넘으면 실패해서 짧은 이름으로 만든 뒤 옮긴다."""
import json, os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / 'tools' / 'hwp-cli' / 'hwp.exe'
CONV = ROOT / 'convert.py'
CORPUS = ROOT / 'corpus' / 'rhwp'
OUT = ROOT / 'corpus' / '_dev_out' / 'engine_compare'


def render(src, dst, work):
    r = subprocess.run([str(EXE), 'render', str(src), '-o', 't.pdf'], capture_output=True, cwd=work, timeout=600)
    if r.returncode == 0 and (work / 't.pdf').exists(): shutil.move(str(work / 't.pdf'), dst); return True
    return False


def main():
    man = [m for m in json.loads((CORPUS / 'manifest.json').read_text(encoding='utf-8')) if 'oracle_pdf' in m]
    for d in ('orig', 'hx'): (OUT / d).mkdir(parents=True, exist_ok=True)
    work = OUT / 'work'; work.mkdir(exist_ok=True)
    for i, m in enumerate(man):
        src = CORPUS / m['path']
        if src.suffix != '.hwp': continue
        stem = src.stem
        render(src, OUT / 'orig' / f'{i:02d}_{stem}.pdf', work)                       # 원본 HWP 를 hwp-cli 로 직접 그림(그 렌더러의 상한)
        for tag in ('ours', 'cli'):
            hx = work / 'x.hwpx'
            if tag == 'ours': r = subprocess.run([sys.executable, str(CONV), str(src), str(hx)], capture_output=True, env={**os.environ, 'HWP_CLI': 'off', 'PYTHONIOENCODING': 'utf-8'})
            else: r = subprocess.run([str(EXE), 'convert', str(src), '-o', 'x.hwpx'], capture_output=True, cwd=work)
            if r.returncode == 0 and hx.exists(): render(hx, OUT / 'hx' / f'{i:02d}_{tag}.pdf', work)
            hx.unlink(missing_ok=True)
        print('done', i, stem, flush=True)
    res = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--read-only', '--tmpfs', '/tmp:size=1g', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--memory', '3g',
                          '-v', f'{CORPUS}:/in:ro', '-v', f'{OUT / "hx"}:/hx:ro', '-v', f'{OUT / "orig"}:/cli:ro', '-v', f'{ROOT / "devtools"}:/t:ro',
                          'pdftest:wp', 'python', '-W', 'ignore', '/t/engcmp2.py'], capture_output=True, text=True, encoding='utf-8', env={**os.environ, 'MSYS_NO_PATHCONV': '1'})
    text = '\n'.join(l for l in res.stdout.splitlines() if 'Fontconfig' not in l)
    (OUT / 'result.txt').write_text(text, encoding='utf-8'); print(text)


if __name__ == '__main__':
    main()

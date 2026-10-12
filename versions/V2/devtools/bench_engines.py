"""엔진별 변환 시간·최대 메모리(RSS)를 문서마다 따로 잰다(한 번에 하나씩, 병렬 없음). 컨테이너(pdftest:wp + /x/rhwp)에서:
    python bench_engines.py 문서경로...   -> 문서 | 우리 초·MB | rhwp 초·MB"""
import os, subprocess, sys, time
RH = ['/x/rhwp', 'export-pdf', '{s}', '-o', '{d}', '--font-path', '/usr/share/fonts', '--fallback-serif', 'NanumMyeongjo', '--fallback-sans', 'NanumGothic', '--fallback-mono', 'NanumGothicCoding']
OURS = [sys.executable, '/work/convert.py', '{s}', '{d}']


def run(cmd, s, d):
    code = ('import resource,subprocess,sys,time;t=time.time();r=subprocess.run(sys.argv[1:],capture_output=True);'
            'print(r.returncode,round(time.time()-t,1),resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss//1024)')
    out = subprocess.run([sys.executable, '-c', code] + [c.format(s=s, d=d) for c in cmd], capture_output=True, text=True, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}).stdout.split()
    return f'{out[1]}초 {out[2]}MB' + ('' if out[0] == '0' else f' (실패 {out[0]})')


for s in sys.argv[1:]:
    print(os.path.basename(s)[:40].ljust(42), '| 우리', run(OURS, s, '/tmp/o.pdf').ljust(20), '| rhwp', run(RH, s, '/tmp/r.pdf'), flush=True)

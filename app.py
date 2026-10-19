"""웹 화면: 파일을 올리면 형식을 판별하고, 고른 형식으로 변환해 내려준다.   실행: .venv\\Scripts\\streamlit run app.py
변환은 서브프로세스로 convert.py를 부른다. hwp2html이 프로세스당 1건을 전제로 하고(동시 접속 충돌 방지), 시간 제한·오류 격리도 얻는다.
요청 기록은 logs/requests.jsonl 한 줄씩(시각·형식·크기·소요시간·결과·입력 해시). 파일명과 본문은 남기지 않는다."""
import hashlib, json, os, subprocess, sys, tempfile, threading, time
from datetime import datetime
from pathlib import Path
import streamlit as st
import convert

HERE = Path(__file__).parent
LOG = HERE / 'logs' / 'requests.jsonl'
NAME = {'hwp': 'HWP', 'hwpx': 'HWPX', 'html': 'HTML'}
MIME = {'hwpx': 'application/hwp+zip', 'html': 'text/html'}
TIMEOUT = 120      # 변환 제한 시간(초). 가장 큰 샘플(66MB)이 2~3초라 넉넉하다. 멈춘 변환이 자리를 오래 잡지 않게 짧게 둔다
MAX_PARALLEL = 3   # 동시에 변환하는 수. 최대 샘플의 메모리가 약 390MB라 3개면 1.2GB 안팎
WAIT = 60          # 자리가 날 때까지 기다리는 시간(초). 넘으면 "바쁨"으로 안내


class Busy(Exception): pass


@st.cache_resource
def slots():
    return threading.BoundedSemaphore(MAX_PARALLEL)      # 세션이 달라도 같은 객체를 쓴다 (스크립트는 상호작용마다 다시 실행되므로 모듈 전역으로는 안 된다)


@st.cache_data(show_spinner=False)
def inspect_upload(data):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'input'; p.write_bytes(data)
        return convert.inspect(p)      # (형식, 판별 근거)


def run(data, target):
    """data를 target 형식으로 변환한 (바이트, 경고 | None). 실패하면 RuntimeError, 시간 초과는 subprocess.TimeoutExpired, 자리가 없으면 Busy."""
    if not slots().acquire(timeout=WAIT): raise Busy
    try:
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d) / 'input', Path(d) / f'output.{target}'
            src.write_bytes(data)
            r = subprocess.run([sys.executable, str(HERE / 'convert.py'), str(src), str(dst)], capture_output=True, text=True,
                               encoding='utf-8', timeout=TIMEOUT, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
            if r.returncode: raise RuntimeError(r.stderr.strip().splitlines()[-1] if r.stderr.strip() else '변환 실패')
            warn = next((l for l in r.stderr.splitlines() if l.startswith('경고:')), None)     # 성공했지만 알려 줄 것(예: □로 보일 문자)
            return dst.read_bytes(), warn
    finally:
        slots().release()


def log(**rec):
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, 'a', encoding='utf-8') as f:      # ponytail: 잠금 없이 한 줄씩 추가. 동시 기록이 잦아지면 잠금이나 DB로
        f.write(json.dumps({'ts': datetime.now().astimezone().isoformat(timespec='seconds'), **rec}, ensure_ascii=False) + '\n')


def convert_logged(data, kind, target):
    """(결과 바이트 | None, 화면에 보일 오류 | None, 소요 초, 경고 | None). 결과는 항상 로그에 한 줄 남긴다."""
    t0, out, err, status, warn = time.time(), None, None, 'ok', None
    try: out, warn = run(data, target)
    except Busy: status, err = 'busy', '지금 변환 요청이 많습니다. 잠시 후 다시 시도하세요.'
    except subprocess.TimeoutExpired: status, err = 'timeout', f'{TIMEOUT}초 안에 끝나지 않아 중단했습니다.'
    except RuntimeError as e: status, err = 'error', f'변환 실패: {e}'
    sec = time.time() - t0
    log(kind=kind, target=target, bytes_in=len(data), bytes_out=len(out) if out else 0, seconds=round(sec, 2), status=status,
        error=err[:200] if err and status == 'error' else None, warning=warn[:200] if warn else None, sha256=hashlib.sha256(data).hexdigest()[:16])
    return out, err, sec, warn


def main():
    st.set_page_config(page_title='파일 변환', page_icon='📄')
    st.title('HWP · HWPX · HTML 변환')
    up = st.file_uploader('변환할 파일을 올리세요', help='형식은 확장자가 아니라 파일 내용으로 판별합니다. 최대 100MB.')
    if up is None: st.stop()
    data = up.getvalue()
    try: kind, why = inspect_upload(data)
    except ValueError as e: st.error(f'변환할 수 없는 파일: {e}'); st.stop()
    st.info(f'판별 결과: **{NAME[kind]}**  ·  {len(data) / 2**20:.1f} MB')
    st.caption(f'판별 근거: {why}')
    target = st.radio('변환할 형식', [t for k, t in convert.ROUTES if k == kind], format_func=str.upper, horizontal=True)
    key = (up.name, len(data), target)
    if st.button('변환', type='primary'):
        with st.spinner('변환 중…'):
            out, err, sec, warn = convert_logged(data, kind, target)
        if err: st.session_state.pop('result', None); st.error(err)
        else: st.session_state['result'] = (key, out, sec, warn)
    res = st.session_state.get('result')
    if res and res[0] == key:     # 다운로드 버튼을 눌러 다시 실행돼도 결과가 남도록 session_state에 둔다
        name = f'{Path(up.name).stem}.{target}'
        st.success(f'완료 · {len(res[1]) / 2**10:,.0f} KB · {res[2]:.1f}초')
        if res[3]: st.warning(res[3])
        st.download_button(f'{name} 내려받기', res[1], name, MIME[target])


if __name__ == '__main__':
    main()

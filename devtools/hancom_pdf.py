"""한글(이 PC 의 한컴오피스)을 오토메이션으로 조종해 문서를 한컴 PDF 로 저장한다 = 채점용 정답 생성기. 앱·변환기와 무관한 개발 도구(윈도 전용, 한글 설치 필요).

    python devtools/hancom_pdf.py --out <폴더> 문서1.hwp 문서2.hwpx ...

- 외부 전송 금지 목록(corpus/no_external.txt)에 있는 문서와 samples/사내/ 는 한글로도 열지 않는다(거절).
- 보안 모듈 DLL(tools/hancom_automation, 출처·체크섬은 SOURCE.md)은 **실행하는 동안만** 레지스트리 HKCU\\SOFTWARE\\HNC\\HwpAutomation\\Modules 에 등록하고,
  끝나면(오류·시간 초과 포함) 지운다. 원래 같은 이름의 값이 있었다면 그 값으로 되돌린다. 등록돼 있는 동안은 어떤 프로그램도 경고 없이 한글으로 파일을 열고 저장할 수 있다.
- PDF 는 한글 '인쇄(PDF 프린터)'와 같은 경로라 문서의 인쇄 설정(2쪽 모아찍기·용지 맞춤)이 그대로 들어간다(예: 40쪽 문서가 모아찍기로 20장). 인쇄 설정과 무관한 쪽 수는 <out>/pagecount.json 의 한컴 쪽 수(`hwp.PageCount`)를 쓴다.
- 이 스크립트가 띄운 한글 프로세스만 끝낸다(원래 열려 있던 한글은 건드리지 않는다).
"""
import argparse, hashlib, json, subprocess, sys, threading, winreg
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DLL = ROOT / 'tools' / 'hancom_automation' / 'FilePathCheckerModuleExample.dll'
KEY, NAME = r'SOFTWARE\HNC\HwpAutomation\Modules', 'FilePathCheckerModuleExample'
FORMAT = {'.hwp': 'HWP', '.hwpx': 'HWPX'}
DLL_SHA256 = '9ac5b97c47ac8aed1e8bca27a3eef39411361d8f68c262509f0c40a8f9d21bb6'      # tools/hancom_automation/SOURCE.md 에 적은 값


def hwp_pids():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Hwp.exe', '/FO', 'CSV', '/NH'], capture_output=True).stdout.decode('mbcs', 'replace')      # 윈도 기본 코드 페이지(cp949)
    return {int(l.split('","')[1]) for l in out.splitlines() if l.startswith('"Hwp.exe"')}


def forbidden(p):
    txt = (ROOT / 'corpus' / 'no_external.txt').read_text(encoding='utf-8') if (ROOT / 'corpus' / 'no_external.txt').exists() else ''
    return '사내' in p.parts or p.name in txt


def register():
    """등록 전 값을 돌려준다(없으면 None)."""
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as k:
        try: old = winreg.QueryValueEx(k, NAME)[0]
        except FileNotFoundError: old = None
        winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, str(DLL))
    return old


def unregister(old):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as k:
        if old is None:
            try: winreg.DeleteValue(k, NAME)
            except FileNotFoundError: pass
        else: winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, old)
        try: left = winreg.QueryValueEx(k, NAME)[0]
        except FileNotFoundError: left = None
    assert left == old, '레지스트리 정리 실패: %r' % left
    print('레지스트리 정리 확인:', '값 없음' if left is None else '원래 값으로 복원')


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', required=True); ap.add_argument('--timeout', type=int, default=300, help='문서 하나당 초'); ap.add_argument('--as', dest='fmt', default='pdf', choices=('pdf', 'hwp', 'both'), help='저장 형식. hwp 는 한컴이 계산한 줄(PARA_LINE_SEG)을 담은 HWP 로 저장 — 합성 시험 문서의 줄 끊김 정답용'); ap.add_argument('files', nargs='+')
    a = ap.parse_args(); out = Path(a.out).resolve(); out.mkdir(parents=True, exist_ok=True)
    todo = []
    for f in a.files:
        p = Path(f).resolve()
        if not p.exists() or p.suffix.lower() not in FORMAT: print('건너뜀(없거나 hwp/hwpx 아님):', p.name); continue
        if forbidden(p): print('거절(외부 전송 금지 목록·사내 문서):', p.name); continue
        todo.append(p)
    if not todo: return 1
    assert DLL.exists(), '보안 모듈 DLL 이 없다(작업 뒤 지웠다면 tools/hancom_automation/SOURCE.md 의 출처에서 다시 받고 해시를 대조): ' + str(DLL)
    assert hashlib.sha256(DLL.read_bytes()).hexdigest() == DLL_SHA256, 'DLL 해시가 SOURCE.md 와 다르다 — 등록하지 않는다'
    import win32com.client
    before, old, hwp, fail, pages = hwp_pids(), None, None, 0, {}
    pj = out / 'pagecount.json'; pages = json.loads(pj.read_text(encoding='utf-8')) if pj.exists() else {}      # 한컴이 센 쪽 수(인쇄 설정·모아찍기와 무관)
    try:
        old = register()
        hwp = win32com.client.Dispatch('HWPFrame.HwpObject')
        mine = lambda: hwp_pids() - before
        assert hwp.RegisterModule('FilePathCheckDLL', NAME), 'RegisterModule 이 False 를 돌려줌(등록 이름·DLL 경로 확인)'
        for p in todo:
            dst = out / (p.stem + ('.hwp' if a.fmt == 'hwp' else '.pdf'))
            dog = threading.Timer(a.timeout, lambda: [subprocess.run(['taskkill', '/F', '/PID', str(x)], capture_output=True) for x in mine()]); dog.start()      # 대화상자 등으로 멈추면 우리가 띄운 한글만 끝낸다
            try:
                ok = hwp.Open(str(p), FORMAT[p.suffix.lower()], 'forceopen:true'); pages[p.name] = hwp.PageCount if ok else None
                if a.fmt in ('hwp', 'both'): ok = ok and hwp.SaveAs(str(out / (p.stem + '.hwp')), 'HWP', '')
                if a.fmt in ('pdf', 'both'): ok = ok and hwp.SaveAs(str(out / (p.stem + '.pdf')), 'PDF', '')
                hwp.Clear(1)      # 변경 버리고 닫기
            except Exception as e: ok = False; print('오류:', p.name, e)
            finally: dog.cancel()
            dst = out / (p.stem + ('.pdf' if a.fmt == 'pdf' else '.hwp'))
            print(('저장' if ok and dst.exists() else '실패'), p.name, '->', dst.name, '| 한컴 쪽 수', pages.get(p.name)); fail += not (ok and dst.exists())
    finally:
        try:
            if hwp is not None: hwp.Quit()
        except Exception: pass
        for x in hwp_pids() - before: subprocess.run(['taskkill', '/F', '/PID', str(x)], capture_output=True)      # 남은 건 우리가 띄운 것만
        pj.write_text(json.dumps(pages, ensure_ascii=False, indent=1), encoding='utf-8'); unregister(old)
        print('남은 새 한글 프로세스:', len(hwp_pids() - before))
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())

# 한글 오토메이션 보안 모듈 (FilePathCheckerModuleExample.dll)

- 출처: 한컴 개발자 페이지(한글 오토메이션 문서)가 안내하는 한컴 공식 GitHub `hancom-io/devcenter-archive` 의 `hwp-automation/보안모듈(Automation).zip`.
  https://github.com/hancom-io/devcenter-archive/raw/main/hwp-automation/%EB%B3%B4%EC%95%88%EB%AA%A8%EB%93%88(Automation).zip
- 받은 날: 2026-10-13 (사용자가 직접 받음). 한컴은 체크섬·서명을 안 알려 줘서 받은 파일로 직접 쟀다.
- SHA-256 `secmod.zip` = 5d87292efafd7311cba6d35e4b416ac8bfa78608a64dde1656c8cb827b051bd8
- SHA-256 `FilePathCheckerModuleExample.dll` = 9ac5b97c47ac8aed1e8bca27a3eef39411361d8f68c262509f0c40a8f9d21bb6
- 확인한 것: 같은 zip 에 든 C++ 소스(`IsAccessiblePath` 가 무조건 TRUE 반환 = 파일 접근 승인 창 안 띄움)와 DLL 이 일치. DLL 은 32비트(한글 `Hwp.exe` 도 32비트), 내보내는 함수는 `IsAccessiblePath` 하나, 가져오는 DLL 은 KERNEL32·USER32 뿐(네트워크·프로세스 생성·레지스트리 쓰기 API 없음). **디지털 서명 없음**(2007 빌드).
- 쓰는 법·위험: `hancom_pdf.py`(각 버전의 `devtools/`)가 실행하는 동안만 `HKCU\SOFTWARE\HNC\HwpAutomation\Modules` 에 값을 쓰고 끝나면(오류 포함) 값을 지운다. 등록돼 있는 동안은 한글을 조종하는 어떤 프로그램도 경고 없이 파일을 열고 저장할 수 있다.
- **사용자 지시**: 2026-10-13 에는 작업이 끝나면 DLL 파일도 지우기로 했으나, 2026-10-19 에 "아직 필요하면 삭제하지 마"로 바뀌어 필요한 동안은 지우지 않는다(`tools/hancom_automation/*.dll`, `secmod*`). 저장소(공개)에는 DLL·압축 파일을 올리지 않는다(`.gitignore`).
- **삭제 기록(2026-10-13 16:15)**: 오토메이션 작업을 마치고 DLL·zip·압축 푼 폴더(Downloads/hancom_secmod)를 지웠다. 레지스트리 값 0개, 한글 프로세스 0개 확인. 다시 쓰려면 위 출처에서 받아 SHA-256 을 위 값과 대조한 뒤 `tools/hancom_automation/` 에 두면 된다(`hancom_pdf.py` 가 실행 전에 DLL 해시를 다시 검사한다).

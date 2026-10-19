# File-conversation (HWP/HWPX/HTML/PDF 변환 공장)

새 세션이면 **먼저 `docs/현재상태.md` 를 읽는다**(기준선·명령·결정·다음 작업. 이력은 `docs/작업기록/`, 함정은 `docs/함정.md`, 형식 지식은 `docs/지식/`; `docs/` 는 개인 문서라 저장소에는 없다). 도구는 `versions/V2/devtools/README.md`.

## 꼭 지킬 것
- `versions/V1` 은 수정 금지. 기존 변환기 개선은 `versions/V2` 에서, rhwp 구조(공통 IR·자체 조판)를 따르는 새 변환기는 `versions/V3` 에서(사용자 지시 2026-10-14, 설계 `docs/설계_rhwp_구조_도입_2026-10-14.md`). 결과물은 `results/V번호_…` 새 폴더에.
- **버전 구분(사용자 지시 2026-10-19)**: V2 는 완성, V3 는 웹 문서 편집 이전까지의 rhwp 구조 변환기, **웹 문서 편집은 `versions/V4`**(V3 복사본 + `edit.py`·`editor.py`). 웹 편집 코드를 V3 에 넣지 않는다.
- **브랜치(사용자 지시 2026-10-19)**: `dev` 에는 자잘한 작업 업데이트를, 버전 브랜치 `V1`~`V4` 에는 그 버전의 기능이 **완성됐을 때만** 올린다. 버전 브랜치는 `python tools/publish_branch.py <V>` 로 루트에 펼쳐 만든 결과물이라(루트 공용 파일 + `versions/<V>/` 내용, README 는 버전 쪽 우선) 직접 고치지 않는다. 푸시는 사용자가 요청할 때만, 미리보기(기본)로 파일 목록을 먼저 보여 준다.
- **HWP→HWPX 만 hwp-cli**(`convert.py` `_hwp_to_hwpx`), HTML·PDF 는 자체 변환기. 바꾸지 말 것(사용자 결정).
- Claude 의 시각 검수(API 호출·화면 판독)는 **외부 전송 금지 목록(`corpus/no_external.txt`, 로컬 전용)에 없는 문서만** 한다(공개 코퍼스와 허용된 `samples/` 문서). 목록에 있는 문서는 숫자 지표로만 본다. 목록을 바꾸려면 사용자에게 먼저 묻는다.
- **테스트 단계에서는 CLI 로 되는 일은 API 를 쓰지 않고 CLI 로 한다**(예: 시각 검수는 `verify_visual.py`(Anthropic API) 대신 `claude -p` 헤드리스 CLI 나 직접 판독). 사용자 지시 2026-10-12.
- `.env` 값을 출력·복사하지 않는다. `requirements.txt` 수정은 먼저 묻는다. 새 외부 실행 파일은 공식 릴리스 + 체크섬 확인.
- 푸시는 사용자가 요청할 때만, **`main` 이 아니라 `dev` 브랜치에 먼저** 올린다(사용자 지시 2026-10-12). `docs/`·`samples/`·`results/`·`corpus/` 는 올리지 않는다.
- 평가(`run_eval.sh`)가 도는 동안에는 `versions/V2` 를 고치지 않는다(평가 컨테이너가 V2 를 그대로 읽는다). 고칠 것은 임시 복사본에서.
- 한 사이클: 수정 → `sh versions/V2/devtools/run_layout.sh`(쪽 수 일치 18/20 이상) → `python test_hwpx_roundtrip.py` → (`verify_visual.py`) → `docker compose up -d --build` → 컨테이너 시험 → 인수인계 문서·메모리 갱신.
- 개별 문서에 맞춘 땜질 금지: 결함 **종류**를 찾아 일반적으로 고친다.
- 한국어로 소통한다. 확인 못 한 것은 "확인 못 했다"고 말한다.

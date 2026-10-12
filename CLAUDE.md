# File-conversation (HWP/HWPX/HTML/PDF 변환 공장)

새 세션이면 **먼저 `docs/인수인계_2026-10-07.md` 를 읽는다**(현재 상태·명령·결정·다음 작업·함정). 도구는 `versions/V2/devtools/README.md`.

## 꼭 지킬 것
- `versions/V1` 은 수정 금지. 개발은 `versions/V2` 에서만. 결과물은 `results/V번호_…` 새 폴더에.
- **HWP→HWPX 만 hwp-cli**(`convert.py` `_hwp_to_hwpx`), HTML·PDF 는 자체 변환기. 바꾸지 말 것(사용자 결정).
- Claude(API) 시각 검수는 **공개 코퍼스(`corpus/rhwp`)만**. `samples/` 사용자 문서를 API 로 보내려면 먼저 승인을 받는다.
- `.env` 값을 출력·복사하지 않는다. `requirements.txt` 수정은 먼저 묻는다. 새 외부 실행 파일은 공식 릴리스 + 체크섬 확인.
- 한 사이클: 수정 → `sh versions/V2/devtools/run_layout.sh`(쪽 수 일치 18/20 이상) → `python test_hwpx_roundtrip.py` → (`verify_visual.py`) → `docker compose up -d --build` → 컨테이너 시험 → 인수인계 문서·메모리 갱신.
- 개별 문서에 맞춘 땜질 금지: 결함 **종류**를 찾아 일반적으로 고친다.
- 한국어로 소통한다. 확인 못 한 것은 "확인 못 했다"고 말한다.

# V3 — rhwp 구조를 따르는 변환기 (웹 문서 편집 이전까지)

HWP·HWPX·HTML 을 서로 바꾸고 PDF 로 내보내는 변환기와 웹 화면(Streamlit)입니다. V2 를 복사해 시작해, 글자 폭 측정과 줄 나눔·쪽 나눔을 한컴이 저장한 값에 맞추는 `core/` 패키지를 더한 버전입니다(사용자 결정 2026-10-14: rhwp 방식을 본받되 깨지는 글자는 자체 변환기로 보완). 웹 문서 편집 기능은 V4 에서 시작합니다(사용자 결정 2026-10-19).

## V2 에서 달라진 점
- **글자 폭 모델과 줄 나눔기**(`core/widthmodel.py`·`metrics.py`·`linebreak.py`·`natural.py`): 한컴 합성 문서로 확인한 규칙(폭 4 HWPUNIT 양자화, 공백 0.5em, 공백 압축)을 따라, 저장된 줄이 없는 문단의 줄 끊김을 직접 계산합니다. 한컴이 저장한 줄 8,484개를 정답으로 한 재현율 92.7%.
- **2패스 위치 되잡기**(`core/vpos.py`): 문단의 세로 위치를 한컴이 저장한 값에 맞춰 위 간격을 고치고 다시 배치하며, 한컴이 쪽을 바꾼 자리에서 우리가 한 쪽에 더 담을 때만 쪽을 나눕니다.
- **글꼴 폭표**: 이 PC 에 설치된 글꼴 파일에서 읽은 폭(`core/data/font_metrics_local.json.gz`)과 rhwp(MIT)의 폭표(`core/data/rhwp_font_metrics.json.gz`, 고지는 `core/data/LICENSE-rhwp-MIT`와 루트 `THIRD_PARTY_NOTICES.md`). 한컴·마이크로소프트 글꼴 파일은 넣지 않았습니다.
- 표 행 나눔·글 감싸기·떠 있는 개체 배치·바탕쪽·쪽 테두리·차트(SVG)·그림 효과 등 V2 이후 고친 점은 `devtools/` 와 저장소의 작업 기록을 따릅니다.

## 평가 기준선 (`devtools/gates.json`)
| 세트 | 쪽 수 일치 | 쪽 오차 합 | 모양 유사도 | 글 위치 오차 dy |
|---|---|---|---|---|
| 공개 코퍼스 102건 | 81 | 44 | 0.595 | 22.8pt |
| 공개 정답지 20건 | — | — | 0.701 | — |
| 사용자 문서 8건 | — | — | 0.671 | — |

기준은 이 PC 의 한컴오피스가 만든 PDF 입니다. 사용자 문서는 저장소에 없습니다.

## 쓰는 법
```sh
docker compose up -d --build        # http://localhost:8502  (이 컴퓨터에서만 접속됨)
python convert.py 입력.hwp 출력.pdf   # .html | .hwpx | .pdf   (PDF 는 WeasyPrint 가 있는 컨테이너에서)
python convert.py --capabilities     # 이 환경에서 되는 변환·옵션·한도(JSON)
python test_hwpx_roundtrip.py        # 회귀 시험
```
환경변수: `NATURAL_BREAKS=off`(CSS 줄 나눔), `VPOS_FIX=off`(위치 되잡기 끔), `STORED_LAYOUT=off`(저장된 줄 무시), `SLACK_FIX=on`(쪽 끝 허용, 기본 꺼짐), `IGNORE_LINESEG=1`(시험용).
`devtools/` 는 평가·진단 도구(쪽 수·글 위치·모양 유사도, 줄 나눔 재현 시험, 합성 문서 생성)이고 사용법은 `devtools/README.md` 에 있습니다. 시험 문서(corpus)·한컴 정답 PDF 는 저장소에 올리지 않습니다.

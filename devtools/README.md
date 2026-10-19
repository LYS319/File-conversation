# devtools — 변환기 개발용 도구 (운영 이미지에는 안 들어간다)

임시 폴더(휘발성)에만 있던 비교·측정 스크립트를 프로젝트로 옮긴 것. **프로젝트 루트(D:\Company_project\File-conversation)에서** 실행한다.

## 준비
| 필요한 것 | 방법 |
|---|---|
| 시험 이미지 `pdftest:wp` | `sh devtools/build_pdftest.sh` (앱 Dockerfile 의 글꼴 목록·fonts.conf 를 바꿨으면 다시 만든다) |
| 공개 코퍼스 `corpus/rhwp/` | rhwp 저장소(github.com/edwardkim/rhwp, MIT)의 샘플 32건 + 한컴 정답 PDF 20건 + `manifest.json`. git 제외 폴더 |
| hwp-cli | `tools/hwp-cli/hwp.exe` (v1.3.1, 윈도) |

## 자주 쓰는 것
| 하는 일 | 명령 |
|---|---|
| 로컬 정확도 점검(쪽 수·글 보존·글 위치·모양 유사도) | `sh devtools/run_eval.sh rhwp\|rhwp2\|user` → `corpus/_eval/<세트>/eval.txt` · 낱말 위치 `diag.sh` · 문단별 저장 줄 위치 `diag_paras.py` |
| 요소 종류별 오차(표 칸 안/본문/머리말·꼬리말) 우리 대 rhwp | `component_diff.py jobs.json out.json [쪽 수]` (컨테이너, rhwp 의 `export-render-tree` 필요) — 어느 요소부터 고칠지 고르는 근거 |
| 글꼴별 글자 폭 비율(한컴 대 우리) | `font_width.py jobs.json out.json` (컨테이너) — 결과로 `hwp2html.HANGUL_DELTA` 를 정한다 |
| 속도·메모리 | `bench_engines.py 문서…` (컨테이너) |
| HWP→HWPX 3엔진 비교(우리·hwp-cli·rhwp) | `python devtools/hwpx_compare.py [--max-mb 10]` (윈도 호스트) |
| 비교용 엔진 rhwp 로 같은 점검 | `ENGINE=rhwp sh devtools/run_eval.sh <세트> [--compat 2022\|2024]` (실행 파일 `tools/rhwp/`, 격리 컨테이너, 글꼴 이름 지정 필수) |
| 쪽 수 점검 (기준선 18/20) | `sh devtools/run_layout.sh` → `corpus/_layout_out/layout_report.txt` |
| 한컴 PDF 와 우리 PDF 를 한 장으로 | `sh devtools/cmp.sh basic/english.hwp 0 0.8` → `corpus/_dev_out/cmp.png`(왼쪽 한컴, 오른쪽 우리) |
| 줄·글 위치 숫자로 비교 | `diag_path.py`(표지 글 위치), `ys2.py`·`xs.py`(줄 y·x), `diag_marks.py`(쪽마다 지정한 글의 위치) — `cmp.sh` 가 만든 `cmp_now.pdf` 를 읽는다 |
| HWP→HWPX 엔진 비교 | `python devtools/engine_compare.py` → `corpus/_dev_out/engine_compare/result.txt` |
| 모양 유사도(HTML 경로) | `engcmp.py`, `engcmp_html.py`(hwp-cli HTML 과 비교) |
| Claude 시각 검수 | `python verify_visual.py corpus/rhwp corpus/_layout_out <출력폴더> [--control]` (공개 코퍼스만! 문서 이미지가 API 로 나간다) |
| 회귀 시험 | `python test_hwpx_roundtrip.py` (호스트, `-I` 없이). 컨테이너 쪽은 인수인계 문서 4장 |
| 평가 두 번 사이 문서별 차이(쪽 수·유사도·dy 가 바뀐 문서만, 변화 큰 순) | `python devtools/evaldiff.py corpus/_eval/<전 폴더> corpus/_eval/<후 폴더>` — 평가 전에 `cp -r corpus/_eval/<세트> corpus/_eval/<세트>_before_X` 로 기준선을 떠 둘 것 |
| 한컴 PDF 쪽 → 우리 PDF 쪽 대응(쪽 첫머리 글로 찾음, 어디서부터 밀리는지) | `python devtools/page_map.py 한컴.pdf 우리.pdf` |
| 한컴·우리 쪽을 한 장에 나란히 보기 | `python devtools/montage.py 출력.png 0.7 한컴.pdf:18 우리.pdf:20 우리.pdf:21` (쪽은 1부터, 이미지는 Read 로 열어 본다) |
| 극단값 문서 3엔진(우리·hwp-cli·rhwp) 비교표 + **문서마다 한컴·우리·hwp-cli·rhwp·차이 나란히 그림**(한컴과 처음 갈라지는 쪽) | `sh devtools/run_extreme_cmp.sh` (그림만: `python devtools/extreme_cmp.py figs 테스트파일/04.극단값 corpus/_extreme_cmp 테스트파일/04.극단값/02.엔진비교_그림`) |
| 표 행 높이(가로선 간격 pt) | `python devtools/hlines.py 한컴.pdf:19 우리.pdf:21` |
| 표 행 나눔 실험(기본 꺼짐) | `SPLIT_ROWS=on sh devtools/run_eval.sh <세트>` (인수인계 문서 2026-10-11 장) |

## 주의
- 스크립트 안의 `/in` `/out` `/work` `/t` 는 컨테이너 안 경로다(도커 `-v` 로 연결).
- `cmp.py` 는 `manifest.json` 에 정답 PDF 가 있는 문서만 찾는다.

# V1 — 처음 발표한 버전 (2026-10-07)

발표 당시의 코드를 그대로 둔 참고용 버전입니다. **수정하지 않습니다.** 이후 개선은 V2(PDF 출력·정확도 평가 도구), V3(글자 폭·줄 나눔·쪽 나눔을 한컴 저장값에 맞춤), V4(웹 문서 편집) 브랜치에 있습니다.

한글(HWP 5.0)·HWPX·HTML 문서를 서로 바꾸는 변환기와, 파일을 올리면 형식을 알아내 원하는 형식으로 내려주는 웹 화면(Streamlit)입니다. 모든 처리는 내 컴퓨터(컨테이너) 안에서만 일어납니다.

> 한글과컴퓨터(한컴)와 무관한 독립 프로젝트입니다. "한글", "한컴", "HWP" 는 각 권리자의 상표·명칭이며, 이 저장소는 공개된 파일 형식 문서와 실제 파일 관찰에 근거해 만들었습니다.

## 지원하는 변환

| 입력 \ 출력 | HTML | HWPX |
|---|---|---|
| **HWP** (5.0) | ✓ | ✓ (HTML 을 거쳐 한 번에) |
| **HWPX** | ✓ | — |
| **HTML** | — | ✓ |

- 입력 형식은 확장자가 아니라 **파일 내용**으로 판별합니다(OLE2 시그니처, ZIP + `mimetype=application/hwp+zip`, HTML 태그). 출력 형식은 출력 파일의 확장자로 정합니다.
- PDF 출력은 V2 부터 있습니다.

## 쓰는 법

필요한 것: Docker.

```sh
docker compose up -d --build        # http://localhost:8501  (이 컴퓨터에서만 접속됨)
```

명령줄로 바로 바꾸려면(의존성을 깐 환경에서):

```sh
python convert.py 입력.hwp 출력.html      # .html | .hwpx
```

## 구성

| 파일 | 내용 |
|---|---|
| `convert.py` | 통합 진입점(형식 판별 + 변환 길 표) |
| `hwp2html.py` · `hwpx2html.py` · `html2hwpx.py` | 변환기 |
| `app.py` | 웹 화면. 변환은 서브프로세스로 `convert.py` 를 불러 동시 접속 충돌을 막고 시간 제한·오류를 격리합니다 |
| `test_hwpx_roundtrip.py` | HWPX↔HTML 왕복 회귀 점검(API 호출 없음): `python test_hwpx_roundtrip.py` |
| `Dockerfile` · `compose.yaml` | 컨테이너 설정 |

보안 설정: 읽기 전용 파일시스템, `cap_drop: ALL`, `no-new-privileges`, 호스트의 `127.0.0.1` 에만 포트 열기, 메모리 3GB·CPU 2개·프로세스 256개 제한. 요청 기록(`logs/requests.jsonl`)에는 시각·형식·크기·소요시간·결과·입력 해시만 남기고 파일 이름과 본문은 남기지 않습니다.

외부 자료와 라이선스는 루트의 `THIRD_PARTY_NOTICES.md` 에 있습니다. 이 저장소 자체의 라이선스는 아직 정하지 않았습니다.

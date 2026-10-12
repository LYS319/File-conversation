#!/bin/sh
# 쪽 수 점검(한컴 정답 PDF 20건과 비교) -> corpus/_layout_out/layout_report.txt (+ NN_이름.pdf). 기준선: 쪽 수 일치 18/20, 차이 합계 2 (2026-10-07)
# 앱과 같은 글꼴의 시험 이미지 pdftest:wp 에서 격리 실행한다(없으면 sh versions/V2/devtools/build_pdftest.sh).
ROOT=$(cd "$(dirname "$0")/../../.." && (pwd -W 2>/dev/null || pwd)); cd "$ROOT" || exit 1
mkdir -p corpus/_layout_out
MSYS_NO_PATHCONV=1 docker run --rm --network none --read-only --tmpfs /tmp:size=1g --cap-drop ALL --security-opt no-new-privileges --memory 3g \
  -v "$ROOT/versions/V2:/work:ro" -v "$ROOT/corpus/rhwp:/in:ro" -v "$ROOT/corpus/_layout_out:/out" \
  pdftest:wp python /work/check_layout.py /in /out

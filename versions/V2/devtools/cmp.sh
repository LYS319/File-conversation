#!/bin/sh
# 사용: sh versions/V2/devtools/cmp.sh 문서끝이름 [쪽(0부터)] [배율]   예) cmp.sh basic/english.hwp 0 0.8
# 한컴 정답 PDF(왼쪽)와 우리 변환 PDF(오른쪽)를 한 장으로 -> corpus/_dev_out/cmp.png  (먼저 pdftest:wp 이미지가 있어야 한다: sh versions/V2/devtools/build_pdftest.sh)
ROOT=$(cd "$(dirname "$0")/../../.." && (pwd -W 2>/dev/null || pwd))
mkdir -p "$ROOT/corpus/_dev_out"
MSYS_NO_PATHCONV=1 docker run --rm --network none --read-only --tmpfs /tmp:size=1g --cap-drop ALL --security-opt no-new-privileges --memory 3g \
  -v "$ROOT/versions/V2:/work:ro" -v "$ROOT/corpus/rhwp:/in:ro" -v "$ROOT/corpus/_dev_out:/out" -v "$ROOT/versions/V2/devtools:/t:ro" \
  pdftest:wp python /t/cmp.py "$@" 2>&1 | grep -a -v Fontconfig

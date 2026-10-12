#!/bin/sh
# 낱말 위치 비교(diag_words.py)를 시험 이미지에서 실행. 사용: sh diag.sh <정답.pdf> <우리.pdf> [쪽] [모아찍기 nup] [개수]   (경로는 프로젝트 루트 기준)
ROOT=$(cd "$(dirname "$0")/../../.." && (pwd -W 2>/dev/null || pwd)); R=$1; O=$2; shift 2
MSYS_NO_PATHCONV=1 docker run --rm --network none --read-only --tmpfs /tmp --cap-drop ALL -v "$ROOT:/r:ro" pdftest:wp python /r/versions/V2/devtools/diag_words.py "/r/$R" "/r/$O" "$@"

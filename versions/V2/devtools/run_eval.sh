#!/bin/sh
# 로컬 정확도 점검(쪽 수·글 보존·글 위치·모양 유사도, 토큰 0·밖으로 안 나감). 인자: 세트 이름 [eval_layout.py 옵션...]
#   sh versions/V2/devtools/run_eval.sh rhwp      # 공개 20건   -> corpus/_eval/rhwp/eval.txt
#   sh versions/V2/devtools/run_eval.sh rhwp2     # 공개 110건
#   sh versions/V2/devtools/run_eval.sh user      # 사용자 문서 8건(samples/ + corpus/*.pdf)
#   ENGINE=rhwp sh versions/V2/devtools/run_eval.sh rhwp2 [--compat 2024]   # 비교용 엔진(tools/rhwp, rhwp v0.8.7)으로 같은 세트 -> corpus/_eval/rhwp2_rhwp/
# 앱과 같은 글꼴의 시험 이미지 pdftest:wp 에서 격리 실행한다(없으면 sh versions/V2/devtools/build_pdftest.sh).
ROOT=$(cd "$(dirname "$0")/../../.." && (pwd -W 2>/dev/null || pwd)); cd "$ROOT" || exit 1
SET=${1:-rhwp}; shift
case "$SET" in
  rhwp)  BASE=/c/rhwp;  MAN=/c/rhwp/manifest.json ;;
  rhwp2) BASE=/c/rhwp2; MAN=/c/rhwp2/manifest.json ;;
  user)  BASE=/c;       MAN=/c/user_manifest.json ;;
  *) echo "세트: rhwp | rhwp2 | user"; exit 1 ;;
esac
ENGINE=${ENGINE:-ours}
OUT="$SET"; [ "$ENGINE" = "rhwp" ] && OUT="${SET}_rhwp"
mkdir -p "corpus/_eval/$OUT"
if [ "$ENGINE" = "rhwp" ]; then
  # tmpfs 는 기본이 noexec 라 실행 파일을 /x(exec 허용 tmpfs)로 복사해 쓴다
  MSYS_NO_PATHCONV=1 docker run --rm --network none --read-only --tmpfs /tmp:size=2g --tmpfs /x:size=100m,exec --cap-drop ALL --security-opt no-new-privileges --memory 6g \
    -v "$ROOT/versions/V2:/work:ro" -v "$ROOT/corpus:/c:ro" -v "$ROOT/samples:/samples:ro" -v "$ROOT/tools/rhwp:/t:ro" -v "$ROOT/corpus/_eval/$OUT:/out" \
    pdftest:wp sh -c 'B=$0; M=$1; shift; cp /t/rhwp /x/rhwp && chmod +x /x/rhwp && python /work/devtools/eval_layout.py "$B" "$M" /out --engine rhwp "$@"' "$BASE" "$MAN" "$@"
else
  [ -n "$STORED_LAYOUT" ] && OUT="${OUT}_stored" && mkdir -p "corpus/_eval/$OUT"       # 실험: 한컴이 저장한 줄 끊김·쪽 시작대로(STORED_LAYOUT=1 sh run_eval.sh …)
  [ -n "$EVAL_TAG" ] && OUT="${OUT}_$EVAL_TAG" && mkdir -p "corpus/_eval/$OUT"       # 실험 꼬리표: EVAL_TAG=s120 SPLIT_ROWS=on SPLIT_MIN=120 sh run_eval.sh user -> corpus/_eval/user_s120 (기준선 폴더를 덮어쓰지 않는다)
  MSYS_NO_PATHCONV=1 docker run --rm --network none --read-only --tmpfs /tmp:size=2g --cap-drop ALL --security-opt no-new-privileges --memory 6g -e STORED_LAYOUT="$STORED_LAYOUT" ${SPLIT_ROWS:+-e SPLIT_ROWS=$SPLIT_ROWS} \
    ${SPLIT_MIN:+-e SPLIT_MIN=$SPLIT_MIN} ${SPLIT_FILL:+-e SPLIT_FILL=$SPLIT_FILL} ${SPLIT_OVER:+-e SPLIT_OVER=$SPLIT_OVER} \
    -v "$ROOT/versions/V2:/work:ro" -v "$ROOT/corpus:/c:ro" -v "$ROOT/samples:/samples:ro" -v "$ROOT/corpus/_eval/$OUT:/out" \
    pdftest:wp python /work/devtools/eval_layout.py "$BASE" "$MAN" /out "$@"
fi

#!/bin/sh
# 로컬 정확도 점검(쪽 수·글 보존·글 위치·모양 유사도, 토큰 0·밖으로 안 나감). 인자: 세트 이름 [eval_layout.py 옵션...]
#   sh devtools/run_eval.sh rhwp      # 공개 20건   -> corpus/_eval/rhwp/eval.txt
#   sh devtools/run_eval.sh rhwp2     # 공개 110건
#   sh devtools/run_eval.sh user      # 사용자 문서 8건(samples/ + corpus/*.pdf)
#   VIA_HTML=1 EVAL_TAG=v sh devtools/run_eval.sh user      # 한글 문서 -> HTML -> PDF 두 단계(사용자의 실제 흐름)로 평가
#   sh devtools/run_eval.sh html      # HTML->PDF 23건(기준 = Edge 인쇄, 먼저 python devtools/make_html_refs.py)
#   ENGINE=rhwp sh devtools/run_eval.sh rhwp2 [--compat 2024]   # 비교용 엔진(tools/rhwp, rhwp v0.8.7)으로 같은 세트 -> corpus/_eval/rhwp2_rhwp/
# 앱과 같은 글꼴의 시험 이미지 pdftest:wp 에서 격리 실행한다(없으면 sh devtools/build_pdftest.sh).
# V3DIR=<폴더>: 평가가 도는 동안 버전 폴더를 고칠 수 있게 복사본으로 평가한다(예: 버전 폴더를 /tmp/snap 으로 복사한 뒤 V3DIR=/tmp/snap sh run_eval.sh …)
ROOT=$(cd "$(dirname "$0")/.." && (pwd -W 2>/dev/null || pwd)); cd "$ROOT" || exit 1
SET=${1:-rhwp}; shift
case "$SET" in
  rhwp)  BASE=/c/rhwp;  MAN=/c/rhwp/manifest.json ;;
  rhwp2) BASE=/c/rhwp2; MAN=/c/rhwp2/manifest.json ;;
  user)  BASE=/c;       MAN=/c/user_manifest.json ;;
  html)  BASE=/c/html;  MAN=/c/html/manifest.json ;;      # HTML -> PDF: 기준은 한컴이 아니라 Edge 인쇄(devtools/make_html_refs.py)
  *) echo "세트: rhwp | rhwp2 | user | html"; exit 1 ;;
esac
ENGINE=${ENGINE:-ours}
OUT="$SET"; [ "$ENGINE" = "rhwp" ] && OUT="${SET}_rhwp"
mkdir -p "corpus/_eval/$OUT"
if [ "$ENGINE" = "rhwp" ]; then
  # tmpfs 는 기본이 noexec 라 실행 파일을 /x(exec 허용 tmpfs)로 복사해 쓴다
  MSYS_NO_PATHCONV=1 docker run --rm --network none --read-only --tmpfs /tmp:size=2g --tmpfs /x:size=100m,exec --cap-drop ALL --security-opt no-new-privileges --memory 6g \
    -v "${V3DIR:-$ROOT}:/work:ro" -v "$ROOT/corpus:/c:ro" -v "$ROOT/samples:/samples:ro" -v "$ROOT/tools/rhwp:/t:ro" -v "$ROOT/corpus/_eval/$OUT:/out" \
    pdftest:wp sh -c 'B=$0; M=$1; shift; cp /t/rhwp /x/rhwp && chmod +x /x/rhwp && python /work/devtools/eval_layout.py "$B" "$M" /out --engine rhwp "$@"' "$BASE" "$MAN" "$@"
else
  [ -n "$STORED_LAYOUT" ] && OUT="${OUT}_stored" && mkdir -p "corpus/_eval/$OUT"       # 실험: 한컴이 저장한 줄 끊김·쪽 시작대로(STORED_LAYOUT=1 sh run_eval.sh …)
  [ -n "$VIA_HTML" ] && OUT="${OUT}_via"       # 한글 문서 -> HTML -> PDF 두 단계 평가는 폴더 이름에 _via
  [ -n "$EVAL_TAG" ] && OUT="${OUT}_$EVAL_TAG" && mkdir -p "corpus/_eval/$OUT"       # 실험 꼬리표: EVAL_TAG=s120 SPLIT_ROWS=on SPLIT_MIN=120 sh run_eval.sh user -> corpus/_eval/user_s120 (기준선 폴더를 덮어쓰지 않는다)
  MSYS_NO_PATHCONV=1 docker run --rm --network none --read-only --tmpfs /tmp:size=2g --cap-drop ALL --security-opt no-new-privileges --memory 6g -e STORED_LAYOUT="$STORED_LAYOUT" ${IGNORE_LINESEG:+-e IGNORE_LINESEG=$IGNORE_LINESEG} ${NATURAL_BREAKS:+-e NATURAL_BREAKS=$NATURAL_BREAKS} ${SPLIT_ROWS:+-e SPLIT_ROWS=$SPLIT_ROWS} \
    ${KEEP_ROWS:+-e KEEP_ROWS=$KEEP_ROWS} ${TBL_FIT:+-e TBL_FIT=$TBL_FIT} ${BODY_BOTTOM:+-e BODY_BOTTOM=$BODY_BOTTOM} ${PAGE_SLACK:+-e PAGE_SLACK=$PAGE_SLACK} ${VPOS_FIX:+-e VPOS_FIX=$VPOS_FIX} ${VPOS_FIRST:+-e VPOS_FIRST=$VPOS_FIRST} ${VPOS_VZ_MAX:+-e VPOS_VZ_MAX=$VPOS_VZ_MAX} ${VPOS_LIMIT:+-e VPOS_LIMIT=$VPOS_LIMIT} ${VPOS_MAXSEC:+-e VPOS_MAXSEC=$VPOS_MAXSEC} ${FIT_MIN:+-e FIT_MIN=$FIT_MIN} ${FIT_MAX:+-e FIT_MAX=$FIT_MAX} ${TRAIL_FIT:+-e TRAIL_FIT=$TRAIL_FIT} ${ALIGN_FIX:+-e ALIGN_FIX=$ALIGN_FIX} ${SPLIT_MIN:+-e SPLIT_MIN=$SPLIT_MIN} ${SPLIT_FILL:+-e SPLIT_FILL=$SPLIT_FILL} ${SPLIT_OVER:+-e SPLIT_OVER=$SPLIT_OVER} ${SLACK_FIX:+-e SLACK_FIX=$SLACK_FIX} ${EVAL_TIMEOUT:+-e EVAL_TIMEOUT=$EVAL_TIMEOUT} ${VPOS_SCORE:+-e VPOS_SCORE=$VPOS_SCORE} ${VPOS_MAXBYTES:+-e VPOS_MAXBYTES=$VPOS_MAXBYTES} ${OVERLAP_FIX:+-e OVERLAP_FIX=$OVERLAP_FIX} ${SLACK_CAP:+-e SLACK_CAP=$SLACK_CAP} \
    -v "${V3DIR:-$ROOT}:/work:ro" -v "$ROOT/corpus:/c:ro" -v "$ROOT/samples:/samples:ro" -v "$ROOT/corpus/_eval/$OUT:/out" \
    pdftest:wp python /work/devtools/eval_layout.py "$BASE" "$MAN" /out ${VIA_HTML:+--via-html} "$@"
fi

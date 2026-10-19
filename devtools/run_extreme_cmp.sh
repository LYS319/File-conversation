#!/bin/sh
# 극단값 문서(테스트파일/04.극단값)를 세 엔진(우리 변환기·rhwp·hwp-cli)으로 PDF 로 바꿔 용량·쪽 수·그림 수·걸린 시간을 비교한다.
#   sh devtools/run_extreme_cmp.sh [ours] [rhwp] [cli]      (인자 없으면 셋 다, 약 30~60분. 시간 비교라 다른 평가를 같이 돌리지 말 것)
# 결과: corpus/_extreme_cmp/{ours,rhwp,cli}.jsonl · pdf_*/ · 표.md   (모두 로컬 처리)
ROOT=$(cd "$(dirname "$0")/.." && (pwd -W 2>/dev/null || pwd)); cd "$ROOT" || exit 1
X="테스트파일/04.극단값"; OUT=corpus/_extreme_cmp; mkdir -p $OUT/pdf_ours $OUT/pdf_rhwp $OUT/pdf_cli
WHAT=${*:-ours rhwp cli}
for e in $WHAT; do
  case $e in
    ours) MSYS_NO_PATHCONV=1 docker run --rm --network none --read-only --tmpfs /tmp:size=3g --cap-drop ALL --security-opt no-new-privileges --memory 6g -e PYTHONUTF8=1 -e HOME=/tmp \
            -v "$ROOT:/work:ro" -v "$ROOT/$X:/e:ro" -v "$ROOT/$OUT:/out" pdftest:wp python /work/devtools/extreme_cmp.py run ours /e /out/ours.jsonl /out/pdf_ours ;;
    rhwp) MSYS_NO_PATHCONV=1 docker run --rm --network none --read-only --tmpfs /tmp:size=3g --tmpfs /x:size=100m,exec --cap-drop ALL --security-opt no-new-privileges --memory 6g -e PYTHONUTF8=1 -e HOME=/tmp \
            -v "$ROOT:/work:ro" -v "$ROOT/$X:/e:ro" -v "$ROOT/tools/rhwp:/t:ro" -v "$ROOT/$OUT:/out" pdftest:wp \
            sh -c 'cp /t/rhwp /x/rhwp && chmod +x /x/rhwp && python /work/devtools/extreme_cmp.py run rhwp /e /out/rhwp.jsonl /out/pdf_rhwp' ;;
    cli)  PYTHONUTF8=1 python devtools/extreme_cmp.py run cli "$X" $OUT/cli.jsonl $OUT/pdf_cli ;;
  esac
done
PYTHONUTF8=1 python devtools/extreme_cmp.py table "$X" $OUT > $OUT/표.md && cat $OUT/표.md
PYTHONUTF8=1 python devtools/extreme_cmp.py figs "$X" $OUT "$X/02.엔진비교_그림"

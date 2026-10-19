#!/bin/sh
# 평가 세트를 세 엔진(우리 · rhwp · hwp-cli)으로 문서 하나씩 차례로 변환해 같은 지표(eval_layout)로 정확도를, 같은 방식으로 시간을 잰다. 모두 로컬.
#   sh devtools/run_engine3.sh [세트…]     (기본 rhwp2 rhwp user, 약 1시간. 시간 비교라 다른 일을 같이 돌리지 말 것)
# 결과: corpus/_eval/<세트>_eng3(우리)·<세트>_rhwp·<세트>_cli 의 eval.json(sec = 문서 하나 변환 벽시계; hwp-cli 는 times.json)
ROOT=$(cd "$(dirname "$0")/.." && (pwd -W 2>/dev/null || pwd)); cd "$ROOT" || exit 1
for S in ${*:-rhwp2 rhwp user}; do
  case "$S" in rhwp) BASE=/c/rhwp; MAN=/c/rhwp/manifest.json ;; rhwp2) BASE=/c/rhwp2; MAN=/c/rhwp2/manifest.json ;; user) BASE=/c; MAN=/c/user_manifest.json ;; esac
  ENGINE=rhwp sh devtools/run_eval.sh $S --workers 1
  EVAL_TAG=eng3 sh devtools/run_eval.sh $S --workers 1
  PYTHONUTF8=1 python devtools/cli_corpus.py $S
  MSYS_NO_PATHCONV=1 docker run --rm --network none --read-only --tmpfs /tmp:size=2g --cap-drop ALL --security-opt no-new-privileges --memory 6g \
    -v "$ROOT:/work:ro" -v "$ROOT/corpus:/c:ro" -v "$ROOT/samples:/samples:ro" -v "$ROOT/corpus/_eval/${S}_cli:/out" \
    pdftest:wp python /work/devtools/eval_layout.py "$BASE" "$MAN" /out --engine none
done
date > corpus/_eval/engine3_done.txt

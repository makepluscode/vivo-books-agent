#!/usr/bin/env bash
# 실행 환경(.venv)과 '목표 환경'(.target-env, 점검 기준이 되는 최신 패키지)을 만들어요.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
python3 -m venv .target-env
# 점검 기준: 설치 시점의 PyPI 최신 안정 버전. 버전을 고정하려면 scripts/target-requirements.txt 를 쓰세요.
REQ=scripts/target-requirements.txt
if [ "${DRIFT_DEMO:-0}" = "1" ]; then
  .target-env/bin/python -m pip install -q -r scripts/demo-requirements.txt
elif [ "${DRIFT_PIN:-0}" = "1" ] && [ -f "$REQ" ]; then
  .target-env/bin/pip install -q -r "$REQ"
else
  .target-env/bin/pip install -q langchain langchain-core langchain-openai langchain-classic openai pandas \
    numpy scikit-learn pydantic matplotlib requests scipy Pillow networkx
  .target-env/bin/pip install -q torch --index-url https://download.pytorch.org/whl/cpu
fi
command -v bwrap >/dev/null || echo "⚠️ bubblewrap(bwrap)이 없어 예제 실행 확인을 건너뛰어요: sudo apt install bubblewrap"
echo "완료. .env 에 LINER_API_KEY 를 넣고: .venv/bin/python -m drift.web"

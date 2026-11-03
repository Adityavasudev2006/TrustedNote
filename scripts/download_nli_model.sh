#!/usr/bin/env bash
# Pre-download the local NLI verifier weights used by: trustnote batch --verifier nli
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
export HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-1}"
echo "Downloading cross-encoder/nli-deberta-v3-small (~568 MB)..."
huggingface-cli download cross-encoder/nli-deberta-v3-small
echo "Verifying load..."
python -c "from trustnote.verification import NLIVerifier; NLIVerifier(); print('NLI model OK')"

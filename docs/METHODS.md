# Methods and attribution

This is an adaptation of published ideas, not an official reproduction.

| Foundation | Applied here | Limitation |
|---|---|---|
| MTS-Dialog / ACI-Bench | Transcript/reference-note pairs and split preservation | No data, trained model, or published baseline reproduction bundled |
| FActScore | Atomic clinical claims and evidence-relative support | Encounter transcript replaces external knowledge; estimated support needs human auditing |
| VERISCORE | Claim extraction, retrieval, verification | No web search and no reproduction of its metric |
| AlignScore | Motivation for text alignment | Optional DeBERTa is general-domain NLI, not AlignScore's checkpoint or training objective |

Primary references:

- MTS-Dialog: https://aclanthology.org/2023.eacl-main.168/
- ACI-Bench: https://www.nature.com/articles/s41597-023-02487-3
- Official ACI-Bench repository: https://github.com/wyim/aci-bench
- FActScore: https://aclanthology.org/2023.emnlp-main.741/
- VERISCORE: https://aclanthology.org/2024.findings-emnlp.552/
- AlignScore: https://aclanthology.org/2023.acl-long.634/
- NLI checkpoint and labels: https://huggingface.co/cross-encoder/nli-deberta-v3-small
- Ollama schema API: https://docs.ollama.com/api/chat
- Starter model: https://ollama.com/library/qwen2.5:3b

Confirm the exact supplied 2025 clinical hallucination paper before attributing specific methods to it. Whisper is out of scope.

Supported requires all details to be grounded. Contradicted requires an explicit conflict for the same subject, time, and attribute. Absence is Unverifiable, not Contradicted. Retrieval misses can also cause Unverifiable. These labels describe grounding, not medical truth.

NLI uses evidence as premise and claim as hypothesis. The fixed checkpoint's published label order is contradiction, entailment, neutral. Do not reuse this order for a different checkpoint without verification. Threshold and margin are uncalibrated defaults. Conflicting high-scoring evidence or overlong windows trigger abstention. Model scores are not clinical confidence.

Hybrid retrieval uses reciprocal-rank fusion: sum(1/(60+rank)), with ranks starting at 1. Retrieval scores are not probabilities. Neighbor windows preserve question-answer context but do not guarantee resolution of long-range dependencies. Dense embeddings may truncate long windows; lexical retrieval indexes full windows.

Valid evidence IDs establish provenance, not entailment. Same-model extraction and verification can share errors. Sentence checks cannot guarantee extraction completeness or clinical correctness. Filtering can remove useful facts. Public benchmark contamination in pretrained models cannot be excluded. Temperature/seed settings do not guarantee identical outputs across runtimes. This MVP performs pretrained inference, not training or fine-tuning.

Gemini provider: https://ai.google.dev/api/generate-content . The optional API adapter uses structured JSON and the same source-only prompts; Gemini is not trained or fine-tuned by this project. Local Ollama remains the default.

# Preliminary experiment

First run the handwritten transcript/corrupted note, then three real validation encounters. Inspect extraction coverage and citations before increasing to 20 examples. Handwritten examples are fixtures, not benchmark results.

## Data and splits

Preserve official train/validation/test splits and transcript variants. ACI-Bench's official repository lists 67 train, 20 validation and three test sets of 40 encounters; confirm your downloaded version. Use training data for prompt development, validation for configuration selection, and untouched test data for final evaluation. Exact-hash checks cannot detect all ASR/human variants of one encounter; check encounter IDs manually. MTS-Dialog short sections and ACI full encounters should be reported separately.

Reference notes are generation-quality targets. They are never passed as verification evidence.

## Controlled comparisons

Generate one original note per encounter. Save its SOAP object as a JSON file and use `--note` to reuse exactly that note across verification configurations.

1. Original note baseline.
2. Same note + BM25 + local LLM verification + sentence filtering.
3. Same note + BM25 + NLI verification + sentence filtering.
4. Same note + hybrid retrieval + NLI verification + sentence filtering.

A detection-only arm leaves the note unchanged, so note-quality metrics cannot improve merely from detection. Filtering changes the note and requires completeness evaluation. Do not change generation, retrieval, and verification together when claiming an isolated ablation.

## Human labels

Label every extracted claim against the FULL transcript. Supported means every detail is grounded; Contradicted requires explicit conflicting evidence; Unverifiable includes absence, ambiguity, and partial support. Record evidence, error category, and criticality in the sheet. Hide predictions during independent labeling and restore them by ID before scoring. Ideally use two annotators with adjudication and relevant clinical expertise. Independently check missing/unfaithful extracted claims and the meaning of original sentences.

Do not silently exclude failed or empty outputs. Report failure counts and reasons.

## Metrics

- Human unsupported rate = (Contradicted + Unverifiable) / all human-labeled claims.
- Verification confusion matrix, per-class precision/recall/F1 and macro-F1.
- Human unsupported rates before and after filtering, plus supported-claim retention. An empty filtered note has undefined unsupported rate, not zero.
- Paired ROUGE-L and fixed-encoder BERTScore against identical reference notes.
- Clinical entity F1 using independent canonical annotations or a documented clinical extractor. Include subject, assertion, time, value and units. The provided scorer compares supplied annotations; it does not extract clinical entities.
- Retrieval recall@k: manually check whether retrieved windows jointly contain sufficient gold evidence for supported/contradicted claims. A matching keyword is not sufficient.
- Extraction coverage and note omissions: independent manual audit; entity and similarity scores alone do not prove clinical completeness.

The included score command calculates claim-level human rates. Retrieval recall, extraction coverage and clinical omission review are manual in this version. Automatic self-label counts are diagnostics, not gold factuality.

Report case count, claim count, failures, model versions and averaging rules. For uncertainty, bootstrap by encounter so correlated claims remain together; bootstrap intervals are a future extension, not implemented here. Twenty cases are preliminary evidence, not a basis for assuming statistical significance.

## Error analysis and reproducibility

Inspect wrong person/family attribution, negation reversal, uncertain diagnosis made definite, historical/current confusion, missing units, wrong dosage, planned/completed confusion, invented normal findings, retrieval misses and extraction failures. Show both a false positive and false negative.

Record dataset version/variant, source files, hashes, model tags and weight digests (`ollama list`), dependency versions (`python -m pip freeze`), hardware, code/prompt version, retrieval configuration, threshold, context length, failures and time. The report records key settings but does not pin all model weights or dependencies automatically.

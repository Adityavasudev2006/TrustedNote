# TrustNote — Gemini + ACI-Bench

Scope: transcript → SOAP note → claims → evidence → verification → filtered draft.
No audio transcription or dashboard. No training/fine-tuning is performed.

## Dataset included and prepared

The full uploaded ACI-Bench corpus is included under `data/aci-bench-corpus`.
Ready-to-use splits are in `data/prepared`: train (67), valid (20), test1 (40), test2 (40), test3 (40), totaling 207 encounters. Import validation found no repeated dataset/encounter IDs or exact transcript overlaps across these challenge splits. The manifest records source hashes.

Original metadata and alternate transcript files are preserved but excluded from the prepared experiment. No dataset download or preparation command is needed.

## Setup and first run

Open this `trustnote` folder in VS Code. Run in PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

Get your own key at https://aistudio.google.com/apikey and set it only in this terminal:

```powershell
$env:GEMINI_API_KEY = "YOUR_KEY"
.\.venv\Scripts\python.exe -m trustnote batch --provider gemini --model gemini-2.5-flash --data data/prepared/valid.jsonl --limit 1 --out outputs/aci_first
```

Open `outputs/aci_first/case-0001/report.md`. No Ollama installation is required. The command makes real API calls; quotas/billing depend on your account. The key is not bundled or saved in reports.

## Output and next steps

Each encounter produces report.md, report.json and annotations.csv. Examine the full transcript, original note, retrieved evidence and all verdicts. Fill human gold labels before claiming verification accuracy. Three cases first, then the 20-case validation set. Keep test splits untouched until configuration selection is complete.

Refer to README.md and docs/EXPERIMENT_PLAN.md for quality metrics, optional local NLI comparison, annotation guidance, and limits. Automated model judgments are not clinical approval.

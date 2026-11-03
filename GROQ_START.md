# Run TrustNote with Groq in Git Bash

Extract this updated ZIP to a new folder, open its trustnote folder in VS Code, and run:

```bash
py -3.11 -m venv .venv
./.venv/Scripts/python.exe -m pip install -e .
```

Open the project **`.env`** file (copy from `.env.example` if needed) and paste your key on the `GROQ_API_KEY=` line. The pipeline loads this file on every run; you do not need to export the key in the terminal.

Interactive clinical note (Git Bash / Linux):

```bash
source .venv/bin/activate   # or .venv/Scripts/activate on Windows
python main.py
```

TrustNote research CLI:

```bash
./.venv/Scripts/python.exe -m trustnote run --provider groq --model openai/gpt-oss-20b --max-output 2048 --request-interval 60 --transcript examples/transcript.txt --out outputs/groq_sample
```

The first command run is a small synthetic transcript, not a benchmark result. Open outputs/groq_sample/report.md when finished. Requests are deliberately spaced at least 60 seconds apart to reduce per-minute quota problems; it can take many minutes with no new terminal output. No Groq SDK is needed.

Then run one real ACI-Bench validation encounter:

```bash
./.venv/Scripts/python.exe -m trustnote batch --provider groq --model openai/gpt-oss-20b --max-output 2048 --request-interval 60 --data data/prepared/valid.jsonl --limit 1 --out outputs/groq_aci1
```

Groq free-tier token limits may still reject a long encounter or daily usage. The exact provider error is shown with the key redacted. A larger interval cannot fix an individual request larger than the token allowance. Do not truncate clinical evidence to force it through. A length error requires a higher --max-output (e.g. 4096), subject to account token limits. No automatic retries or intermediate checkpoints are implemented, so interrupted cases start again.

The adapter uses strict structured output on a supported model and locally validates every response. Schema compliance is not clinical accuracy. Original dataset and all prepared splits remain included. Gemini and Ollama remain selectable.

No live Groq call has been tested here because your API key is only on your machine. Offline adapter tests cover request construction, response parsing, incomplete-output rejection and error redaction.

Official docs: https://console.groq.com/docs/structured-outputs and https://console.groq.com/docs/rate-limits

# Validation status

The 15 offline tests passed on Python 3.12 with Pydantic 2.13.5. They cover exact evidence offsets, long-line coverage, adjacent-turn retrieval, invalid citations, conservative context rejection, note preservation/filtering, an extraction-omission sentence guard, dataset column mapping, duplicate/split checks, and metric arithmetic.

Model judgments in these tests are explicitly mocked fixtures. They do not measure clinical model performance.

Ollama, NLI/MiniLM/BERTScore model weights, were unavailable in this environment. Actual inference quality, clinical accuracy, retrieval recall, optional ML dependencies, memory use and runtime must be tested on the user's machine. No benchmark results, trained weights or hidden fallback predictions are included.

Gemini extension: seven additional offline adapter tests cover provider selection, schema/auth request construction, token/model metadata, absent credentials, incomplete/invalid output, and sanitized quota errors without retries. No live Gemini request was made because no API key was provided. These checks do not establish clinical accuracy or confirm a particular account's model access.

Corpus integration: 3 additional fixture-based tests cover the five-split import, metadata exclusion, duplicate-encounter rejection before writing, and preservation of existing output. Total: 25 offline tests. The uploaded benchmark has now been imported and validated: 207 rows, expected five split sizes, no duplicate encounter identities or exact transcript overlap.

Final bundle: original archive members preserved byte-for-byte, prepared records checked against source CSV rows. Gemini live inference remains untested without an API key. No measured clinical benchmark accuracy is claimed.

Groq extension: four additional offline tests cover structured request/auth, parsing, incomplete outputs and redacted provider errors. Total 29 tests. Live Groq inference remains untested.

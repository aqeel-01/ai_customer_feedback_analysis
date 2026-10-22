# AI Customer Feedback & Support Ticket Analyzer

An enterprise-grade, automated customer intelligence system that ingests incoming support tickets (from CSV or JSON), filters out non-actionable noise (greetings, spam, promotions) without wasting LLM tokens, classifies actionable tickets using LLMs (Groq API), enforces strict schema validation (Pydantic), guarantees atomic SQLite persistence, and exports structured results directly into `output/results.json`.

---

## 1. Project Overview & Features

Support operations receive hundreds of tickets daily, many of which are greetings ("Hi", "Hello") or promotional spam. Manually sorting these or blindly routing them to LLMs wastes valuable agent time and API budget.

### Key Implemented Features:
1. **Multi-Source Ingestion (`CSV` & `JSON`)**: Automatically detects file type, trims whitespace, standardizes fields, and validates incoming data via Pydantic (`RawTicket`).
2. **Noise & Spam Pre-Filtering**: Zero-cost, deterministic rule engine that detects greetings and marketing spam, logging them directly to the database as `IGNORED` without calling the LLM.
3. **LLM Extraction & Reasoning**: Analyzes qualifying messages via Groq to extract:
   - **Category**: `Bug Report`, `Feature Request`, `Billing Issue`, `General Inquiry`
   - **Priority**: `Low`, `Medium`, `High`, `Urgent`
   - **Sentiment**: `Positive`, `Neutral`, `Negative`
   - **Product/Feature**: Identified product component or `null`
   - **Suggested Reply**: Empathetic, context-specific suggested draft for human review
4. **Prompt Injection Defense**: Customer messages are treated as untrusted input inside XML boundaries (`<customer_message>`), preventing prompt hijacking.
5. **Deduplication & Safety**: Checks ticket IDs against SQLite before processing to prevent accidental re-processing and redundant API billing.
6. **Audit Trail & Persistence**: Stores all tickets (`PROCESSED`, `IGNORED`, `INVALID`, `FAILED`) in SQLite with full foreign-key constraints.
7. **Primary JSON Output**: Irrespective of whether input is CSV or JSON, all final analyzed tickets are saved in `output/results.json`.
8. **Offline Mock Mode (`--mock`)**: Full end-to-end pipeline verification without requiring API keys or internet connection.

---

## 2. File & Directory Structure

```text
ai_customer_feedback_project/
├── data/
│   ├── sample_input.csv          # Sample tickets in CSV format (greetings, bugs, billing)
│   └── sample_input.json         # Equivalent sample tickets in JSON format
├── feedback_analyzer/
│   ├── db/
│   │   ├── connection.py         # SQLite connection manager with WAL & foreign keys
│   │   ├── repository.py         # Parameterized SQL queries for tickets & analysis
│   │   └── schema.sql            # DDL schema for tickets and analysis_results tables
│   ├── export/
│   │   ├── csv_exporter.py       # Exporter utilities for CSV format
│   │   └── json_exporter.py      # Exporter utilities for JSON format
│   ├── filtering/
│   │   └── filter.py             # Rule-based filter for greetings and spam
│   ├── ingestion/
│   │   ├── csv_reader.py         # Safe CSV reader with encoding fallback
│   │   ├── json_reader.py        # Safe JSON reader with array validation
│   │   └── __init__.py           # load_records() dispatcher
│   ├── llm/
│   │   ├── analyzer.py           # Validates AI output against Pydantic schema
│   │   ├── client.py             # Groq API client with retries and exponential backoff
│   │   └── prompts.py            # Secure prompt engineering & injection safeguards
│   ├── schemas/
│   │   ├── analysis_schema.py    # Strict Pydantic models & permitted enums
│   │   └── input_schema.py       # Input validation & sanitization schema
│   ├── config.py                 # Environment configuration loader (.env)
│   ├── constants.py              # Canonical domain enums
│   ├── logging_setup.py          # Secure structured logging (redacts secrets)
│   └── orchestrator.py           # 7-stage workflow coordinator & offline mock engine
├── output/
│   ├── feedback.db               # SQLite database (audit log, persistence, deduplication)
│   ├── results.json              # Primary output deliverable: analyzed records
│   └── all_tickets.json          # Complete audit log (processed, ignored, and failed)
├── tests/
│   ├── e2e/                      # End-to-end integration scenarios
│   ├── integration/              # Pipeline & exporter integration tests
│   └── unit/                     # Unit test suites (filter, ingestion, DB, LLM, schemas)
├── .env.example                  # Environment configuration template
├── .gitignore                    # Excludes secrets, databases, and caches
├── main.py                       # CLI application entry point
├── requirements.txt              # Production runtime dependencies
├── requirements-dev.txt          # Development, testing, and linting dependencies
└── README.md                     # System documentation
```

---

## 3. How the Pipeline Works

```text
Input File (.csv / .json)
        │
        ▼
[1. Ingestion & Validation] ──> (Invalid records recorded to DB as INVALID)
        │
        ▼
[2. Duplicate Check] ─────────> (Existing IDs skipped to avoid double charges)
        │
        ▼
[3. Noise Filtering] ─────────> (Greetings/Spam recorded to DB as IGNORED, no LLM call)
        │
        ▼
[4. LLM Analysis via Groq] ───> (Prompt injection shielded, JSON mode)
        │
        ▼
[5. Pydantic Validation] ────> (Enforces strict enums & structure)
        │
        ▼
[6. SQLite Persistence] ─────> (Atomic transaction with foreign keys)
        │
        ▼
[7. JSON Export] ─────────────> (Saved directly to output/results.json)
```

---

## 4. Setup Instructions (Windows PowerShell)

### Prerequisites:
- **Python 3.11+**
- (Optional) Free [Groq API Key](https://console.groq.com) for live LLM mode.

### Installation:
```powershell
# 1. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 3. Configure environment (for live LLM analysis)
Copy-Item .env.example .env
# Open .env and insert your key: GROQ_API_KEY=gsk_your_key_here
```

---

## 5. Execution Commands

> **Important:** Always activate your virtual environment in PowerShell first:
> ```powershell
> .\.venv\Scripts\Activate.ps1
> ```

### A. Run in Offline / Mock Mode (Recommended for testing — No API key needed)
Processes data through the complete pipeline with mocked deterministic AI analysis:
```powershell
# Run with CSV input:
.\.venv\Scripts\Activate.ps1
python main.py --input data/sample_input.csv --mock

# Run with JSON input:
python main.py --input data/sample_input.json --mock
```

### B. Run in Live Mode (Uses real Groq API)
```powershell
.\.venv\Scripts\Activate.ps1
python main.py --input data/sample_input.csv
```

### CLI Arguments Reference:
- `--input`, `-i`: Path to input file (`.csv` or `.json`) *(Required)*
- `--mock`, `-m`: Run in offline mode without requiring Groq API credentials
- `--format`, `-f`: Export format (`json` by default, also supports `both` or `csv`)
- `--output-dir`, `-o`: Directory where output files are saved (default: `output`)
- `--db-path`, `-d`: Custom SQLite database path (default: `output/feedback.db`)
- `--log-level`, `-l`: Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`)

---

## 6. How to View Results & Reset for Fresh Runs

### Where to View Results:
Regardless of whether you provided CSV or JSON input, the primary deliverable is saved in:
📁 **`output/results.json`**

Open `output/results.json` to inspect the analyzed records with all 5 AI-extracted fields:
- `category`
- `priority`
- `sentiment`
- `product_or_feature`
- `suggested_reply`

### How to Reset to Avoid Deduplication:
By design, the system **prevents duplicate processing** of already analyzed tickets to protect against accidental re-billing. If you run the pipeline twice on the same file, you will see `Duplicate Records Skipped: 15`.

To reset the database, run this single command in PowerShell:

```powershell
Remove-Item output\feedback.db
```

After resetting, running any analysis command will process all tickets fresh.

---

## 7. Testing & Quality Assurance

The codebase includes comprehensive test suites across unit, integration, and E2E layers:

```powershell
# Run the complete test suite (142 tests):
pytest -k "not test_live_groq_api_call"

# Run with test coverage report (98% coverage):
pytest --cov=feedback_analyzer --cov-report=term-missing -k "not test_live_groq_api_call"

# Run code formatting and linter checks:
ruff check feedback_analyzer tests main.py
```

### Verified Test Scenarios:
1. **Critical Bug**: *"The payment page crashes every time I click 'Checkout' on Chrome..."* → Classified as `Bug Report`, `Urgent`, `Negative`.
2. **Feature Request**: *"Hi team, it would be awesome if you could add a dark mode..."* → Classified as `Feature Request`, `Medium`, `Positive`.
3. **Greeting Noise**: *"Hello, hope you are having a nice day!"* → Filtered as `IGNORED` with reason `Greeting message without actionable request`, 0 LLM calls made.
4. **Resilience**: Malformed CSV rows, invalid JSON, database rollback, SQL injection attempts, and API network retries all pass.

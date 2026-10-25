# PawPal AI Planner

PawPal AI Planner extends [PawPal+](https://github.com/antunishdPursuit-coursework-archive/ai110-module2show-pawpal-starter), the AI110 Module 2 Show. The original Python/Streamlit app registers pets, schedules care, and shows a daily plan across pets. Its scheduler supports sorting, pet/status filters, exact-start-time conflicts, daily/weekly next occurrences, and custom intervals.

This separate repository preserves the original history. The approved extension adds a calendar, Gemini-assisted typed task planning, editable confirmation, location search links, and local saving. Implementation proceeds in verified increments; the initial copied app remains runnable.

## Setup

Use Python 3.11 or newer, from this repository in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env locally and set GEMINI_API_KEY; never commit it.
python -m streamlit run app.py --server.address 127.0.0.1
```

Do not overwrite an existing .env when configuring credentials.

## Design

- [System architecture source](diagrams/architecture.mmd)
- [Storage ERD source](diagrams/erd.mmd)
- [Original domain UML](diagrams/uml_final.mmd)
- [Original PawPal+ walkthrough and evidence](docs/pawpal_baseline.md)

The architecture and ERD describe the approved extension. The AI proposes tasks; deterministic validation and the owner's confirmation precede writes. Gemini does not directly write to storage. The existing CLI remains available through `python main.py`.

## Existing checks

Keep the six original tests unchanged:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -B -m pytest -p no:cacheprovider -q
```

## Course

[AI110 Applied AI System](https://courses.codepath.org/courses/ai110/unit/8#!projects). Voice, guided tours, cloud sync, and duration-based scheduling are outside this version.

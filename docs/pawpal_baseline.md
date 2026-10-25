# PawPal+ — Module 2 Project

PawPal+ is a Python and Streamlit pet-care planner. An owner can register pets,
add care tasks, and view today's schedule across all pets. The scheduler sorts
by time, filters by pet or status, warns about matching start times, and creates
the next daily or weekly task after completion.

## Setup and run

From the repository folder in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
python -m streamlit run app.py
```

Stop Streamlit with Ctrl+C. Data lives in `st.session_state`: it survives normal
app reruns, but is not saved to a database or guaranteed across browser sessions.
Setting the owner's name again preserves the registered pets and tasks.

## System design

- `Owner` owns zero or more pets. `get_all_tasks()` returns all their tasks,
  including completed history, in a new list.
- `Pet` stores its task occurrences and checks pet assignment when adding one.
- `Task` stores the title, description, assigned pet, optional time and schedule,
  and completion date. Its status is `pending`, `overdue`, or `done`.
- `Schedule` represents daily, weekly, or custom intervals in days.
- `Scheduler.get_daily_tasks(owner)` reads `Owner.get_all_tasks()` and applies
  the daily-view rules. Both the CLI and Streamlit app use this path.

See [the class diagram](class_diagram.md) and its
[Mermaid source](diagrams/uml_final.mmd).

## Smarter Scheduling

| Feature | Method | Behavior |
| --- | --- | --- |
| Owner-wide daily plan | `Scheduler.get_daily_tasks` | Collects all pets' tasks through Owner; includes due/overdue tasks and optionally today's completions. Future tasks and old completed history stay outside today's view. |
| Sorting | `Scheduler.sort_by_time` | Sorts native time values earliest first; untimed tasks come last. |
| Filtering | `Scheduler.filter_tasks` | Combines status and pet-name filters. Completed tasks remain available to the UI's done filter. |
| Recurrence | `Scheduler.complete_and_reschedule` | A completed daily/weekly occurrence stays done and creates one new task due one/seven days after completion. Repeating completion adds nothing. |
| Custom intervals | `Task.mark_complete` | Advances the same custom task to completion date plus its interval; it is done today and becomes pending/overdue again when appropriate. |
| Conflicts | `Scheduler.detect_conflicts` | Groups unfinished tasks at the exact same start time, within or across pets. Tasks without a time do not generate a warning. |

Unscheduled tasks are available today. A conflict is a warning, not an automatic
reschedule. The app excludes completed work from conflict warnings and shows
Pending, Overdue, and Done today counts.

## Sample Output

Actual output from `python -B main.py` on October 2, 2026. Dates change when run
on another day. The demo uses Jordan, Rex, Luna, and seven out-of-order tasks.

```text
=============================================
  CONFLICT REPORT
=============================================
  WARNING: CONFLICT at 08:00 AM: 'Bath Time' (Rex) vs 'Morning Feed' (Luna)
  WARNING: CONFLICT at 10:00 AM: 'Grooming' (Luna) vs 'Medicine' (Luna)

=============================================
  TODAY'S SCHEDULE (sorted) — 2026-10-02
  Owner: Jordan
=============================================
  [PENDING] 07:00 AM  Morning Feed
            1 cup of dry food
  [PENDING] 08:00 AM  Bath Time
            Quick rinse after walk
  [PENDING] 08:00 AM  Morning Feed
            Half can of wet food
  [PENDING] 10:00 AM  Grooming
            Brush coat for 5 minutes
  [PENDING] 10:00 AM  Medicine
            Flea prevention drops
  [PENDING] 02:00 PM  Vet Checkup
            Annual vaccination
  [PENDING] 06:00 PM  Walk
            Evening walk, 20 minutes

--- Completing Rex's Morning Feed (DAILY) ---

--- Completing Rex's Walk (CUSTOM — no new instance expected) ---

--- Completing Luna's Grooming (WEEKLY) ---

Rex's full task list after reschedule:
  Walk | due: 2026-10-04 | status: done
  Morning Feed | due: 2026-10-02 | status: done
  Vet Checkup | due: 2026-10-02 | status: pending
  Bath Time | due: 2026-10-02 | status: pending
  Morning Feed | due: 2026-10-03 | status: pending

Luna's full task list after reschedule:
  Grooming | due: 2026-10-02 | status: done
  Morning Feed | due: 2026-10-02 | status: pending
  Medicine | due: 2026-10-02 | status: pending
  Grooming | due: 2026-10-09 | status: pending

Today's pending tasks (any pet):
  08:00:00  Bath Time [pending]
  08:00:00  Morning Feed [pending]
  10:00:00  Medicine [pending]
  14:00:00  Vet Checkup [pending]

Today's done tasks (any pet):
  07:00:00  Morning Feed [done]
  10:00:00  Grooming [done]
  18:00:00  Walk [done]

Only Luna's tasks today:
  08:00 AM  Morning Feed [pending]
  10:00 AM  Grooming [done]
  10:00 AM  Medicine [pending]

Only Rex's pending tasks today:
  08:00 AM  Bath Time [pending]
  02:00 PM  Vet Checkup [pending]

=============================================
```

## Testing PawPal+

The six existing tests in `tests/test_pawpal.py` cover completion dates, task
addition, chronological sorting with untimed tasks last, next-day recurrence,
and positive/negative exact-time conflicts. No tests were added or changed for
this update.

```powershell
python -m pytest
```

Verification used Python 3.14.5, pytest 9.1.0, and Streamlit 1.58.0. To avoid
unrelated global pytest plugins and generated bytecode/cache files, the actual
local command was:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -B -m pytest -p no:cacheprovider -q
```

Actual result on October 2, 2026:

```text
......                                                                   [100%]
6 passed in 0.02s
```

Additional temporary, in-memory checks covered Owner-to-Scheduler retrieval,
cross-pet conflicts, daily/weekly dates, repeated completion, next-day behavior,
and an empty owner. Streamlit's in-memory app runner checked owner setup,
adding a pet and task, completion, the done filter, and updating the owner name.
It reported no app exceptions; completion changed Done today from 0 to 1 and
left one future occurrence. These checks created no test files.

Confidence: **4/5 for the demonstrated local workflow**. The six saved tests
cover only the behaviors listed above. The additional checks are not a saved
regression suite. No browser visual review, durable storage, or duration-based
overlap checking is claimed.

## Demo Walkthrough

1. Run `python main.py` to see the owner-wide schedule, two conflict warnings,
   daily/weekly recurrence, completed tasks, and pet/status filtering. Its
   actual output appears under Sample Output above.
2. Run `python -m streamlit run app.py`. Enter an owner name and select
   **Set Owner**. Add two pets with **Add Pet**.
3. Assign a task to each pet. Choose Daily, Weekly, or Custom, optionally set
   a time, then select **Add Task**. Add tasks out of chronological order to
   see the scheduler sort them.
4. Give two unfinished tasks the same start time. Read the named conflict
   warnings. Untimed tasks sort last and do not produce a conflict.
5. Select **Mark done** on a daily task. The completed task remains visible,
   Done today increases, and one next occurrence is due tomorrow. A weekly
   task's next occurrence is due seven days later.
6. Select **done** in **Filter by status**, then filter by pet. Change the
   owner's name with **Set Owner**; the pets and tasks remain in the session.

The existing [pet_app.PNG](pet_app.PNG) is a historical screenshot, not evidence
of this update's UI verification.

## Course sources and scope

- [Current Week 4 Show: PawPal+](https://courses.codepath.org/courses/ai110/unit/4#!projects)
- [Official starter](https://github.com/codepath/ai110-module2show-pawpal-starter)
- [Project reflection](reflection.md)

The current Show walkthrough specifies time/frequency scheduling, an
Owner-to-Scheduler data path, sorting, filtering, recurrence, conflicts,
verification, and the final diagram. The starter's broad scenario also mentions
duration, priority, editing, and constraint-based planning. This implementation
follows the detailed Show workflow: it does not implement duration/priority
optimization or a task-editing UI. Exact start-time warnings do not measure
interval overlap. Optional stretch features are outside this update.

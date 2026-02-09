# First Year Schedule - SYSC4907

First year schedule program for SYSC4907 project.

---

## Setup

### 1. Create Data Directory

Create a `data` folder in the root directory and add the following files:

- `FY-scheduleData.csv`
- `programReqs.json`
- `programSize.csv`
- `schedSample 1.csv`

### 2. Initialize Database

```bash
python manage.py migrate
python manage.py load_courses
python manage.py load_programs
python manage.py load_program_sizes
python manage.py load_program_reqs
```

✅ **Setup complete!**

---

## Running the Frontend

```bash
python manage.py runserver
```

Open **http://127.0.0.1:8000/** in your browser.

---

## CLI Alternative

You can also run everything from the Django shell (`python manage.py shell`):

```python
from data_app.services.schedule_builder import ScheduleBuilder
builder = ScheduleBuilder()
builder.generate_schedule()
builder.export_schedule_to_txt()
builder.export_visual_grid()

from data_app.services.ranking import ScheduleRanker
ranker = ScheduleRanker()
ranker.rank_all_blocks()
ranker.export_ranking_report()
```

---

## Frontend Guide

### Pages

| Page | URL | Purpose |
|------|-----|---------|
| **Dashboard** | `/` | Overview of all programs with stats and ranking summaries |
| **Program Detail** | `/program/<id>/` | Per-program view with block timetables and course tables |
| **Rankings** | `/rankings/` | All blocks ranked by schedule quality score (0–100) |
| **Generate** | `/generate/` | Trigger schedule generation and ranking |

### Quick-Start Workflow

1. Go to **Generate** (`/generate/`).
2. Click **"Generate New Schedule"** — wait for it to complete.
3. Click **"Rank All Blocks"** — wait for ranking to finish.
4. Go to **Dashboard** — view program cards with scores.
5. Click any program — explore block timetables.
6. Go to **Rankings** — compare all blocks.

### Dashboard

- Shows total programs, enrolled students, blocks, and unique courses.
- Each program card displays enrollment, block count, scheduled courses, and average ranking.
- Click a card to open that program's detail page.

### Program Detail

- **Hero section** — enrollment count, block count, required course counts per term.
- **Required Courses** — fall and winter course codes listed as pill badges.
- **Term Tabs** — filter blocks by All / Fall / Winter.
- **Block Cards** — click a header to expand and see:
  - **Visual Timetable** — weekly grid (Mon–Fri, 8AM–10PM) with color-coded course blocks. Hover for tooltips.
  - **Table View** — click "Toggle Table View" for a detailed list with course code, section, type, days, time, and enrollment bar.
  - **Missing Courses** — yellow warning if required courses couldn't be scheduled.

### Rankings

- Stats: total blocks, average/highest/lowest score.
- Score distribution bars (Excellent 85+, Good 70–84, Fair 50–69, Poor <50).
- Full table of all blocks sorted by score. Use the **"Filter by program"** dropdown to narrow results.
- Click **"Re-rank All Blocks"** in the top bar to re-run ranking.

### Generate

- **"Generate New Schedule"** — builds blocks and assigns course sections. Replaces any existing schedule.
- **"Rank All Blocks"** — scores each block 0–100 (disabled until a schedule exists).
- Both buttons show a loading overlay and stream log output to a console area on the page.
- The "How It Works" panel explains the 5-step algorithm: Build Blocks → Prioritize Courses → Assign Sections → Kick & Repair → Rank & Report.

### Ranking Colors

| Color | Range | Meaning |
|-------|-------|---------|
| 🟢 Green | 85–100 | Excellent |
| 🔵 Blue | 70–84 | Good |
| 🟡 Yellow | 50–69 | Fair |
| 🔴 Red | < 50 | Poor |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "No Programs Found" on Dashboard | Run the data loading commands from [Setup](#2-initialize-database). |
| Generate button disabled | No programs loaded. Load data first. |
| Rank button disabled | No schedule exists. Generate one first. |
| Loading spinner stuck | Check the `runserver` terminal for errors. Refresh and retry. |
| Styles/JS not loading | Ensure `DEBUG=True` in settings, or run `python manage.py collectstatic` for production. |
| Server Error (500) | Check terminal for traceback. Common causes: missing data files or unmigrated DB. |
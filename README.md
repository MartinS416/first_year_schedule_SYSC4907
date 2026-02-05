# First Year Schedule - SYSC4907

First year schedule program for SYSC4907 project

---

## Project Initialization

### 1. Create Data Directory

Create a `data` folder in the root directory:
```
/backend
/data_app
/data          ← create this folder
```

### 2. Add Data Files

Insert the following data files into the `/data` folder:

- `FY-scheduleData.csv`
- `programReqs.json`
- `programSize.csv`
- `schedSample 1.csv`

### 3. Run Migrations

Navigate to the root directory (where `manage.py` is located) and run:
```bash
python manage.py migrate
```

### 4. Load Data into Database

Run the following commands **in order**:
```bash
python manage.py load_courses
python manage.py load_programs
python manage.py load_program_sizes
python manage.py load_program_reqs
```

✅ **Setup complete!**

---

## Testing

### Open Django Shell
```bash
python manage.py shell
```

### Run Test Commands

Copy and paste the following into the shell terminal:
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
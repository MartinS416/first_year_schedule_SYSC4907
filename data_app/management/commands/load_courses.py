import csv
from django.core.management.base import BaseCommand
from data_app.models import Course


class Command(BaseCommand):
    help = "Load course data from FY-scheduleData TSV file"

    def handle(self, *args, **kwargs):
        # Update this path if needed
        path = "data/FY-scheduleData.csv"  # or .tsv, content is TSV

        # Load all rows into memory for two-pass processing
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t")
            rows = list(reader)

        # ------------------------------
        # PASS 1 — Create all Course rows
        # ------------------------------
        for r in rows:
            course_code = f"{r['SUBJ'].strip()} {r['CRSE'].strip()}"
            section = r["SECT"].strip()

            Course.objects.update_or_create(
                course_code=course_code,
                section=section,
                defaults={
                    "term": r["TERM"].strip().lower(),
                    "instr_type": r["INSTR_TYPE"].strip(),
                    "days": r["DAYS"].strip(),  # can be M, W, F, TR, MWF etc.
                    "start_time": r["START_TIME"].strip()
                        if r.get("START_TIME") else "",
                    "end_time": r["END_TIME"].strip()
                        if r.get("END_TIME") else "",
                    "capacity": int(r["ROOM_CAP"])
                        if r.get("ROOM_CAP") and r["ROOM_CAP"].isdigit()
                        else None,
                    "parent": None,
                }
            )

        # ------------------------------
        # PASS 2 — Assign parents
        # ------------------------------
        for r in rows:
            course_code = f"{r['SUBJ'].strip()} {r['CRSE'].strip()}"
            section = r["SECT"].strip()
            term = r["TERM"].strip()

            try:
                course = Course.objects.get(
                    course_code=course_code,
                    section=section
                )
            except Course.DoesNotExist:
                continue

            # Parent detection:
            #
            # Child sections have >1 chars AND start with a letter
            #   A01 → parent = A
            #   A02 → parent = A
            #   B03 → parent = B
            #
            # Parent must be:
            #   - same course_code
            #   - same term
            #   - instr_type == LEC
            #   - section == first letter (A, B, C ...)
            #
            if len(section) > 1 and section[0].isalpha():
                parent_section = section[0]  # first character, e.g., A

                parent = Course.objects.filter(
                    course_code=course_code,
                    term=term.lower(),
                    section=parent_section,
                    instr_type="LEC"
                ).first()

                if parent:
                    course.parent = parent
                    course.save()

        self.stdout.write(self.style.SUCCESS("Course import complete."))
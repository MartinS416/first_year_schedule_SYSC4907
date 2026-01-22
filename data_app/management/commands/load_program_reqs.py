import json
from django.core.management.base import BaseCommand
from data_app.models import Program, ProgramCourse


class Command(BaseCommand):
    help = "Load program requirements from programReqs.json into ProgramCourse table"

    def handle(self, *args, **kwargs):

        path = "data/programReqs.json"  # adjust if needed

        # Load JSON file
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to open {path}: {e}"))
            return

        for program_name, term_data in data.items():

            # --- Find program ---
            program = Program.objects.filter(program_name=program_name).first()

            if not program:
                self.stdout.write(self.style.WARNING(
                    f"Program not found: {program_name}, skipping..."
                ))
                continue

            # --- For each term: fall, winter, extra ---
            for term in ["fall", "winter", "extra"]:
                if term not in term_data:
                    continue  # skip missing terms

                for course_code in term_data[term]:

                    ProgramCourse.objects.update_or_create(
                        program=program,
                        course_code=course_code,
                        defaults={
                            "term": term.lower()
                        }
                    )

                    self.stdout.write(self.style.SUCCESS(
                        f"Added {course_code} ({term}) to {program_name}"
                    ))

        self.stdout.write(self.style.SUCCESS("Program requirements loaded successfully."))

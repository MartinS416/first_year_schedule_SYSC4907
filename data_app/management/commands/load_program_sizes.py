import csv
from django.core.management.base import BaseCommand
from data_app.models import Program


class Command(BaseCommand):
    help = "Load program enrollment sizes from programSize.csv"

    def handle(self, *args, **kwargs):
        path = "data/programSize.csv"  # adjust if your file is somewhere else

        try:
            with open(path, encoding="utf-8") as f:
                reader = csv.DictReader(f)

                for row in reader:
                    program_name = row["name"].strip()
                    enrolled_value = row["enrolled"].strip()

                    # Ensure enrolled is a valid integer
                    try:
                        enrolled = int(enrolled_value)
                    except ValueError:
                        self.stdout.write(self.style.WARNING(
                            f"Invalid enrolled value '{enrolled_value}' for {program_name}, skipping..."
                        ))
                        continue

                    # Check if the program exists
                    program = Program.objects.filter(program_name=program_name).first()

                    if not program:
                        self.stdout.write(self.style.WARNING(
                            f"Program not found: {program_name}, skipping..."
                        ))
                        continue

                    # Update
                    program.enrolled = enrolled
                    program.save()

                    self.stdout.write(self.style.SUCCESS(
                        f"Updated {program_name}: enrolled={enrolled}"
                    ))

        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(
                f"File not found: {path}. Place your CSV in the /data folder."
            ))
            return

        self.stdout.write(self.style.SUCCESS("Program size import complete."))

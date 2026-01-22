import json
from django.core.management.base import BaseCommand
from data_app.models import Program

class Command(BaseCommand):
    help = "Load program names from programReqs.json"

    def handle(self, *args, **kwargs):
        path = "data/programReqs.json"

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for program_name in data.keys():
            Program.objects.get_or_create(program_name=program_name)

        self.stdout.write(self.style.SUCCESS("Programs loaded successfully."))

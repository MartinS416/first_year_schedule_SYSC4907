import math
from django.utils import timezone
from data_app import models
from data_app.models import Course, Program, Block, ProgramCourse, Term, Student
import random
from django.db import models

class ScheduleBuilder:

    BLOCK_SIZE = 20

    SHARED_COURSES = {}

    def build_blocks(self):
        """
        Docstring for build_blocks
        
        :param self: Description
        """
        for program in Program.objects.all():
            self._build_blocks_for_program(program)

    def _build_blocks_for_program(self, program: Program):
        enrolled = program.enrolled or 0

        if enrolled <= 0:
            print(f"Error : Program {program.program_name} has no enrolled students.")
            return
    
        num_blocks = math.ceil(enrolled / self.BLOCK_SIZE)
        
        print(f"Building blocks for program: {program.program_name} with {enrolled} enrolled students.")

        #Delete old blocks
        Block.objects.filter(program=program).delete()

        for i in range(num_blocks):
            block_name = f"Block {chr(ord('A') + i)}"

            block = Block.objects.create(
                program=program,
                block_name=block_name,
                ranking=0,
                timestamp=timezone.now()
            )

            Term.objects.create(block = block, term_name = "Fall")
            Term.objects.create(block = block, term_name = "Winter")
            
        print(f"Created {num_blocks} blocks for program: {program.program_name}")

    def find_shared_courses(self):
        """
        Creates a list of shared courses across all programs ordered by frequency.
        """
        course_stats = (
            ProgramCourse.objects
            .values('course_code')
            .annotate(program_count=models.Count('program', distinct = True))
        )

        enriched_stats = []
        for entry in course_stats:
            code = entry['course_code']

            component_count = Course.objects.filter(course_code=code).count()

            enriched_stats.append({
                'course_code':code,
                'program_count':entry['program_count'],
                'complexity': component_count,
                'random_weight': random.random()
            })

        enriched_stats.sort(
            key=lambda x: (x['program_count'], -x['complexity'], x['random_weight']),
            reverse=True
        )

        return enriched_stats
    
    def get_course_bundles(self, course_code):
        """
        Return a list of all possible course bundles for a given course code.
        """
        parents = Course.objects.filter(
            course_code=course_code,
            parent__isnull=True
        )
        
        bundles = []

        for parent in parents:
            children = parent.children.all()

            labs = [c for c in children if c.instr_type =="LAB"]
            tuts = [c for c in children if c.instr_type =="TUT"]

            if not labs and not tuts:
                bundles.append([parent])
                continue

            for lab in (labs or [None]):
                for tut in (tuts or [None]):
                    bundle = [parent]
                    if lab: bundle.append(lab)
                    if tut: bundle.append(tut)
                    bundles.append(bundle)

        return bundles
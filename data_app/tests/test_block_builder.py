from django.test import TestCase
from data_app.models import Program, Block, Term
from data_app.services.schedule_builder import ScheduleBuilder

class BlockBuilderTests(TestCase):

    def test_build_blocks_creates_correct_number(self):
        program = Program.objects.create(
            program_name="Software Eng",
            enrolled=83
        )

        ScheduleBuilder().build_blocks()

        blocks = Block.objects.filter(program=program)
        self.assertEqual(blocks.count(), 5) 

    def test_each_block_has_two_terms(self):
        program = Program.objects.create(
            program_name="Mechanical Eng",
            enrolled=40
        )

        ScheduleBuilder().build_blocks()

        blocks = Block.objects.filter(program=program)

        for block in blocks:
            terms = Term.objects.filter(block=block)
            self.assertEqual(terms.count(), 2)
            term_names = set(t.term_name for t in terms)
            self.assertEqual(term_names, {"fall", "winter"})
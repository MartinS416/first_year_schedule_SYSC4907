from django.test import TestCase
from data_app.models import Program, Block, Term, Course, TermCourses
from data_app.services.schedule_builder import ScheduleBuilder
from data_app.services.ranking import ScheduleRanker

class RankingLogicTests(TestCase):
    def setUp(self):
        from django.utils import timezone
        self.program = Program.objects.create(program_name="RankTest", enrolled=10)
        self.block = Block.objects.create(program=self.program, block_name="Block A", ranking=0, size=10, timestamp=timezone.now())
        self.term = Term.objects.create(block=self.block, term_name="fall")

    def test_gap_penalty_applied(self):
        # Create two courses with a large gap on the same day
        c1 = Course.objects.create(course_code="C1", section="A", instr_type="LEC", days="M", start_time="0900", end_time="1000", capacity=20, enrolled=0)
        c2 = Course.objects.create(course_code="C2", section="A", instr_type="LEC", days="M", start_time="1300", end_time="1400", capacity=20, enrolled=0)
        TermCourses.objects.create(term=self.term, course_code="C1", section="A")
        TermCourses.objects.create(term=self.term, course_code="C2", section="A")
        score = ScheduleRanker().score_block(self.block)
        self.assertLess(score, 100, "Gap penalty should reduce score below 100")

    def test_sleep_penalty_applied(self):
        # Create two courses, one late Mon, one early Tue, not enough overnight rest
        c1 = Course.objects.create(course_code="C1", section="A", instr_type="LEC", days="M", start_time="2100", end_time="2200", capacity=20, enrolled=0)
        c2 = Course.objects.create(course_code="C2", section="A", instr_type="LEC", days="T", start_time="0700", end_time="0800", capacity=20, enrolled=0)
        TermCourses.objects.create(term=self.term, course_code="C1", section="A")
        TermCourses.objects.create(term=self.term, course_code="C2", section="A")
        score = ScheduleRanker().score_block(self.block)
        self.assertLess(score, 100, "Sleep penalty should reduce score below 100")

class OptimizationTests(TestCase):
    def setUp(self):
        from django.utils import timezone
        self.program = Program.objects.create(program_name="OptTest", enrolled=20)
        self.block = Block.objects.create(program=self.program, block_name="Block O", ranking=0, size=20, timestamp=timezone.now())
        self.term = Term.objects.create(block=self.block, term_name="fall")
        # Add two courses with a gap (to allow optimization to improve)
        self.c1 = Course.objects.create(course_code="C1", section="A", instr_type="LEC", days="M", start_time="0900", end_time="1000", capacity=30, enrolled=0)
        self.c2 = Course.objects.create(course_code="C2", section="A", instr_type="LEC", days="M", start_time="1300", end_time="1400", capacity=30, enrolled=0)
        TermCourses.objects.create(term=self.term, course_code="C1", section="A")
        TermCourses.objects.create(term=self.term, course_code="C2", section="A")

    def test_optimize_schedule_improves_score(self):
        builder = ScheduleBuilder()
        before = ScheduleRanker().score_block(self.block)
        builder.optimize_schedule()
        self.block.refresh_from_db()
        after = ScheduleRanker().score_block(self.block)
        self.assertGreaterEqual(after, before, "Optimization should not decrease block score")

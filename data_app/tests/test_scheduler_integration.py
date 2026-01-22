from django.test import TestCase
from data_app.models import Program, Block, Term, Course, ProgramCourse, TermCourses
from data_app.services.schedule_builder import ScheduleBuilder

class SchedulerIntegrationTests(TestCase):

    def setUp(self):
        self.builder = ScheduleBuilder()
        self.builder.BLOCK_SIZE = 20

        # 1. Create Program
        self.prog = Program.objects.create(program_name="Engineering", enrolled=20)

        # 2. Create Requirement (Program needs MATH100 in Fall)
        ProgramCourse.objects.create(
            program=self.prog, course_code="MATH100", term="fall"
        )

    def test_successful_schedule_generation(self):
        """
        Integration: Full run. 
        Should successfully schedule a course when time and capacity allow.
        """
        # Create Course with capacity 30 (Block is 20, so it fits)
        c1 = Course.objects.create(
            course_code="MATH100", section="A", instr_type="LEC",
            days="MWF", start_time="0900", end_time="1000",
            capacity=30, enrolled=0, parent=None
        )

        # Run Generator
        self.builder.generate_schedule()

        # Check Results
        # 1. TermCourses should exist
        links = TermCourses.objects.filter(course_code="MATH100")
        self.assertTrue(links.exists())
        self.assertEqual(links.first().term.term_name, "fall")

        # 2. Course enrollment should be updated
        c1.refresh_from_db()
        self.assertEqual(c1.enrolled, 20)

    def test_schedule_fails_due_to_capacity(self):
        """
        Integration: Capacity Limit.
        Block size is 20, Course Capacity is 10. Should fail to schedule.
        """
        c1 = Course.objects.create(
            course_code="MATH100", section="A", instr_type="LEC",
            days="MWF", start_time="0900", end_time="1000",
            capacity=10, enrolled=0, parent=None # Capacity too low
        )

        self.builder.generate_schedule()

        # Check Results
        links = TermCourses.objects.filter(course_code="MATH100")
        self.assertFalse(links.exists(), "Should not schedule if capacity is exceeded")
        
        c1.refresh_from_db()
        self.assertEqual(c1.enrolled, 0)

    def test_schedule_fails_due_to_time_conflict(self):
        """
        Integration: Time Conflict.
        We will manually add a course to the term, then try to generate 
        another course that overlaps.
        """
        # Add a second requirement
        ProgramCourse.objects.create(
            program=self.prog, course_code="PHYS100", term="fall"
        )

        # Course 1: MATH100 (MWF 9-10)
        math = Course.objects.create(
            course_code="MATH100", section="A", instr_type="LEC",
            days="MWF", start_time="0900", end_time="1000",
            capacity=100, parent=None
        )

        # Course 2: PHYS100 (MWF 9:30-10:30) - Overlaps!
        phys = Course.objects.create(
            course_code="PHYS100", section="A", instr_type="LEC",
            days="MWF", start_time="0930", end_time="1030",
            capacity=100, parent=None
        )

        self.builder.generate_schedule()

        # Check Results
        math_links = TermCourses.objects.filter(course_code="MATH100").count()
        phys_links = TermCourses.objects.filter(course_code="PHYS100").count()

        # One should succeed, the other should fail.
        # Since logic sorts by "difficulty", usually one gets priority.
        # We assert that they are NOT BOTH scheduled.
        self.assertNotEqual(math_links + phys_links, 2, "Both overlapping courses were scheduled")
        self.assertTrue(math_links == 1 or phys_links == 1, "At least one should be scheduled")

    def test_bundle_selection(self):
        """
        Integration: Bundle Choice.
        If Section A is full, it should pick Section B.
        """
        # Section A: Capacity 5 (Too small for block of 20)
        Course.objects.create(
            course_code="MATH100", section="A", instr_type="LEC",
            days="MWF", start_time="0900", end_time="1000",
            capacity=5, parent=None
        )

        # Section B: Capacity 50 (Fits!)
        Course.objects.create(
            course_code="MATH100", section="B", instr_type="LEC",
            days="TR", start_time="1400", end_time="1530",
            capacity=50, parent=None
        )

        self.builder.generate_schedule()

        link = TermCourses.objects.filter(course_code="MATH100").first()
        self.assertIsNotNone(link)
        self.assertEqual(link.section, "B", "Should pick Section B because A is too small")
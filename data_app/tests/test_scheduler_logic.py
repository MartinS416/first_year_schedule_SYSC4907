from django.test import TestCase
from data_app.models import Program, Block, Term, Course, ProgramCourse, TermCourses
from data_app.services.schedule_builder import ScheduleBuilder

class SchedulerLogicTests(TestCase):

    def setUp(self):
        self.builder = ScheduleBuilder()
        self.builder.BLOCK_SIZE = 20

        # Create a basic program
        self.program = Program.objects.create(
            program_name="Computer Science",
            enrolled=45 # Should result in 3 blocks (20, 20, 5)
        )

    def test_build_blocks_logic(self):
        """
        Test if blocks are created with correct sizing and ranking.
        """
        self.builder.build_blocks()

        blocks = Block.objects.filter(program=self.program)
        self.assertEqual(blocks.count(), 3)
        
        # Check specific sizes based on 45 students / size 20
        b1 = blocks.get(block_name="Block A")
        b2 = blocks.get(block_name="Block B")
        b3 = blocks.get(block_name="Block C")
        
        self.assertEqual(b1.size, 20)
        self.assertEqual(b2.size, 20)
        self.assertEqual(b3.size, 5)

        # Check Terms creation
        self.assertEqual(Term.objects.filter(block=b1).count(), 2) # Fall + Winter

    def test_get_course_bundles(self):
        """
        Test if the builder correctly groups Lectures with their Labs/Tutorials.
        """
        # Parent (Lecture)
        lec = Course.objects.create(
            course_code="CS101", section="A", instr_type="LEC", parent=None
        )
        # Child 1 (Lab 1)
        lab1 = Course.objects.create(
            course_code="CS101", section="L1", instr_type="LAB", parent=lec
        )
        # Child 2 (Lab 2)
        lab2 = Course.objects.create(
            course_code="CS101", section="L2", instr_type="LAB", parent=lec
        )

        bundles = self.builder.get_course_bundles("CS101")
        
        # Should return 2 lists: [Lec, Lab1] and [Lec, Lab2]
        self.assertEqual(len(bundles), 2)
        
        # Verify content of first bundle
        bundle_sections = [c.section for c in bundles[0]]
        self.assertIn("A", bundle_sections)
        self.assertTrue("L1" in bundle_sections or "L2" in bundle_sections)

    def test_has_capacity(self):
        """
        Test the capacity check logic.
        """
        c1 = Course.objects.create(course_code="TEST", enrolled=10, capacity=30)
        c2 = Course.objects.create(course_code="TEST2", enrolled=29, capacity=30)
        
        # Bundle 1: Plenty of space (10 + 15 <= 30)
        self.assertTrue(self.builder._has_capacity([c1], block_size=15))
        
        # Bundle 2: Not enough space (29 + 2 > 30)
        self.assertFalse(self.builder._has_capacity([c2], block_size=2))

    def test_time_parsing_and_intervals(self):
        """
        Test helper functions for time conversion.
        """
        # Test parse_time
        mins = self.builder.parse_time("0830")
        self.assertEqual(mins, 510) # 8*60 + 30

        mins_pm = self.builder.parse_time("1400")
        self.assertEqual(mins_pm, 840)

        # Test formatting helper (if you added it)
        fmt = self.builder._format_time("0930")
        self.assertEqual(fmt, "09:30")

    def test_conflict_logic_direct(self):
        """
        Test the conflict detection directly.
        """
        from data_app.services.schedule_builder import can_add_group_to_term, expand_course, slots_conflict

        # Course A: Mon 10:00 - 11:00
        cA = Course.objects.create(
            course_code="A", days="M", start_time="1000", end_time="1100"
        )
        # Course B: Mon 10:30 - 11:30 (Overlap)
        cB = Course.objects.create(
            course_code="B", days="M", start_time="1030", end_time="1130"
        )
        # Course C: Tue 10:00 - 11:00 (No Overlap)
        cC = Course.objects.create(
            course_code="C", days="T", start_time="1000", end_time="1100"
        )

        # Test A vs B (Conflict)
        self.assertFalse(can_add_group_to_term([cB], [[cA]]))

        # Test A vs C (Safe)
        self.assertTrue(can_add_group_to_term([cC], [[cA]]))
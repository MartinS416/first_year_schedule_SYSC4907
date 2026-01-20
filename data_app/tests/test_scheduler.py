import random
from unittest.mock import patch
from django.test import TestCase
from data_app.models import Program, Course, ProgramCourse
from data_app.services.schedule_builder import ScheduleBuilder

class TestFindSharedCourses(TestCase):
    def setUp(self):
        """Set up programs and requirements for testing."""
        # 1. Create Programs
        self.mech = Program.objects.create(program_name="Mech Eng")
        self.civil = Program.objects.create(program_name="Civil Eng")
        self.elec = Program.objects.create(program_name="Elec Eng")

        # 2. Create Courses (The actual sections/components)
        # PHY101 has 3 components (LEC, LAB, TUT) -> High Complexity
        Course.objects.create(course_code="PHY101", section="A", instr_type="LEC")
        Course.objects.create(course_code="PHY101", section="L1", instr_type="LAB")
        Course.objects.create(course_code="PHY101", section="T1", instr_type="TUT")

        # MATH101 has 1 component (LEC) -> Low Complexity
        Course.objects.create(course_code="MATH101", section="A", instr_type="LEC")

        # 3. Create Requirements (ProgramCourse)
        # MATH101 is needed by all 3 programs
        ProgramCourse.objects.create(program=self.mech, course_code="MATH101", term="Fall")
        ProgramCourse.objects.create(program=self.civil, course_code="MATH101", term="Fall")
        ProgramCourse.objects.create(program=self.elec, course_code="MATH101", term="Fall")

        # PHY101 is needed by 2 programs
        ProgramCourse.objects.create(program=self.mech, course_code="PHY101", term="Fall")
        ProgramCourse.objects.create(program=self.civil, course_code="PHY101", term="Fall")

    @patch('random.random')
    def test_find_shared_courses_sorting(self, mock_random):
        """Verify that courses are sorted by program count then complexity."""
        # Force random to always return 0.5 for stability during test
        mock_random.return_value = 0.5
        
        builder = ScheduleBuilder()
        results = builder.find_shared_courses()

        # Print results for visibility
        print("\n--- Shared Courses Test Results ---")
        for res in results:
            print(f"Code: {res['course_code']} | Programs: {res['program_count']} | Complexity: {res['complexity']}")

        # Assertions
        # MATH101 should be first because it has 3 programs vs PHY101's 2 programs
        self.assertEqual(results[0]['course_code'], "MATH101")
        self.assertEqual(results[0]['program_count'], 3)
        
        # PHY101 should be second
        self.assertEqual(results[1]['course_code'], "PHY101")
        self.assertEqual(results[1]['complexity'], 3)

    def test_empty_database(self):
        """Test behavior when no requirements exist."""
        ProgramCourse.objects.all().delete()
        builder = ScheduleBuilder()
        results = builder.find_shared_courses()
        
        print("\n--- Empty DB Test Result ---")
        print(results)
        self.assertEqual(len(results), 0)


from django.test import TestCase
from data_app.models import Course
from data_app.services.schedule_builder import ScheduleBuilder

class TestCourseBundling(TestCase):
    def setUp(self):
        self.builder = ScheduleBuilder()
        self.course_code = "SYSC2006"

        # 1. Create a Lecture (Parent)
        self.lec_a = Course.objects.create(
            course_code=self.course_code,
            section="A",
            instr_type="LEC",
            parent=None
        )

        # 2. Create two possible Labs for Section A
        self.lab_a1 = Course.objects.create(
            course_code=self.course_code,
            section="A1",
            instr_type="LAB",
            parent=self.lec_a
        )
        self.lab_a2 = Course.objects.create(
            course_code=self.course_code,
            section="A2",
            instr_type="LAB",
            parent=self.lec_a
        )

        # 3. Create a Tutorial for Section A
        self.tut_a1 = Course.objects.create(
            course_code=self.course_code,
            section="T1",
            instr_type="TUT",
            parent=self.lec_a
        )

    def test_bundle_combinations(self):
        """
        Verify that 1 Lec with 2 Labs and 1 Tut results in 2 distinct bundles.
        Bundle 1: [Lec A, Lab L1, Tut T1]
        Bundle 2: [Lec A, Lab L2, Tut T1]
        """
        bundles = self.builder.get_course_bundles(self.course_code)

        print("\n--- Course Bundle Test Results ---")
        for i, bundle in enumerate(bundles):
            names = [f"{c.instr_type} ({c.section})" for c in bundle]
            print(f"Bundle {i+1}: {names}")

        # Assertions
        self.assertEqual(len(bundles), 2, "Should have created exactly 2 bundles for the 2 labs.")
        
        # Check that each bundle starts with the Lecture
        for bundle in bundles:
            self.assertEqual(bundle[0].instr_type, "LEC")
            self.assertEqual(len(bundle), 3, "Each bundle should have Lec, Lab, and Tut.")

    def test_standalone_lecture(self):
        """Test a course that has no labs or tutorials."""
        Course.objects.create(course_code="MATH1001", section="A", instr_type="LEC")
        
        bundles = self.builder.get_course_bundles("MATH1001")
        self.assertEqual(len(bundles), 1)
        self.assertEqual(bundles[0][0].course_code, "MATH1001")
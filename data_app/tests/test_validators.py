from django.test import SimpleTestCase
from data_app.services.schedule_validator import can_add_group_to_term, course_conflict, group_conflicts_with_term, can_add_group_to_term


class FakeCourse:
    """Mocks the Django Course model for utility testing."""
    def __init__(self, days, start_time, end_time, course_code="TEST101"):
        self.days = days
        self.start_time = start_time
        self.end_time = end_time
        self.course_code = course_code

class ValidatorTests(SimpleTestCase):
    def setUp(self):
        # 09:00 - 10:00 (540 - 600)
        self.c1 = FakeCourse("MW", "0900", "1000", "LEC1")
        # 10:00 - 11:00 (600 - 660) - Back to back with c1 (No conflict)
        self.c2 = FakeCourse("MW", "1000", "1100", "LEC2")
        # 09:30 - 10:30 (570 - 630) - Overlaps with both c1 and c2
        self.c_overlap = FakeCourse("M", "0930", "1030", "LAB1")
        # 09:00 - 10:00 (540 - 600) - Same time as c1 but different day
        self.c_friday = FakeCourse("F", "0900", "1000", "TUT1")

    def test_course_conflict_basic(self):
        """Test direct conflict between two course objects."""
        self.assertTrue(course_conflict(self.c1, self.c_overlap), "Should conflict: overlapping times on Monday")
        self.assertFalse(course_conflict(self.c1, self.c2), "Should NOT conflict: back-to-back times")
        self.assertFalse(course_conflict(self.c1, self.c_friday), "Should NOT conflict: different days")

    def test_group_conflicts_with_term_positive(self):
        """Should return True if a new group (e.g. LEC+LAB) hits an existing course."""
        # The term already has LEC1
        term_courses = [[self.c1]]
        # We try to add a group that contains the overlapping LAB
        new_group = [self.c_overlap, self.c_friday]
        
        self.assertTrue(group_conflicts_with_term(new_group, term_courses))

    def test_group_conflicts_with_term_negative(self):
        """Should return False if the new group fits perfectly into the schedule."""
        term_courses = [[self.c1], [self.c2]]
        new_group = [self.c_friday]
        
        self.assertFalse(group_conflicts_with_term(new_group, term_courses))

    def test_can_add_group_to_term_wrapper(self):
        """Verify the boolean inversion of the wrapper function."""
        term_courses = [[self.c1]]
        # Conflict exists
        self.assertFalse(can_add_group_to_term([self.c_overlap], term_courses))
        # No conflict
        self.assertTrue(can_add_group_to_term([self.c_friday], term_courses))
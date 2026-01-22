import pytest
from data_app.services.utils import expand_course, slots_conflict, intervals_overlap, parse_time

class FakeCourse:
    def __init__(self, days, start_time, end_time):
        self.days = days
        self.start_time = start_time
        self.end_time = end_time


def test_parse_time():
    assert parse_time("0900") == 540 
    assert parse_time("1330") == 810 
    assert parse_time("0000") == 0

def test_intervals_overlap():
    # Case: Overlapping
    assert intervals_overlap(600, 700, 650, 750) is True
    # Case: B inside A
    assert intervals_overlap(600, 800, 650, 700) is True
    # Case: Touching (Should NOT conflict)
    assert intervals_overlap(600, 660, 660, 720) is False
    # Case: Distinct
    assert intervals_overlap(600, 660, 700, 800) is False

def test_expand_course_formatting():
    c = FakeCourse("MW", "0900", "1030")
    slots = expand_course(c)
    
    expected = {
        "M": [(540, 630)],
        "W": [(540, 630)]
    }
    assert slots == expected

def test_slots_conflict_complex():
    # Course A: Monday 9:00 - 10:00
    # Course B: Monday 10:00 - 11:00 (No conflict)
    # Course C: Monday 09:30 - 10:30 (Conflict with A)
    
    a = {"M": [(540, 600)]}
    b = {"M": [(600, 660)]}
    c = {"M": [(570, 630)]}

    assert slots_conflict(a, b) is False 
    assert slots_conflict(a, c) is True

def test_expand_course_empty_handling():
    c = FakeCourse(None, None, None)
    assert expand_course(c) == {}
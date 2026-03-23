
def parse_time(t: str) -> int:
    """"
    Parse time string in "HHMM" format to integer minutes since midnight.
    """
    t = int(t)
    return (t // 100) * 60 + (t % 100)

def parse_days(days: str) -> list[str]:
    """
    Parse days string into a list of individual day characters.
    """
    if not days:
        return []
    return list(days.strip())

def expand_course(course):
    """
    Returns:
    {
        "M": [(540, 600), (610, 670)],
        "W": [(540, 600)],
    }
    """
    if not course.days or not course.start_time or not course.end_time:
        return {}
    
    start = parse_time(course.start_time)
    end = parse_time(course.end_time)

    slots = {}

    for d in parse_days(course.days):
        slots.setdefault(d, []).append((start, end))

    return slots

def intervals_overlap(a_start, a_end, b_start, b_end):
    """
    Returns True if two time intervals overlap.
    """
    return not(a_end <= b_start or b_end <= a_start)

def slots_conflict(slots_a, slots_b):
    """
    Returns True if there is a conflict between two sets of course slots.
    """
    for day in slots_a:
        if day not in slots_b:
            continue

        for (s1, e1) in slots_a[day]:
            for (s2, e2) in slots_b[day]:
                if intervals_overlap(s1, e1, s2, e2):
                    return True
                
    return False

from data_app.models import Course
from django.db.models import F

def check_course_capacities():
    exceeding_courses = Course.objects.filter(
        capacity__isnull=False, 
        enrolled__gt=F('capacity')
    )
    
    if not exceeding_courses.exists():
        print("All courses are perfectly within their capacity limits!")
        return
        
    print(f"WARNING: Found {exceeding_courses.count()} courses exceeding capacity:")
    print("-" * 65)
    print(f"{'Course Code':<15} | {'Section':<8} | {'Term':<10} | {'Enrolled':<10} | {'Capacity':<10}")
    print("-" * 65)
    
    for course in exceeding_courses:
        print(f"{course.course_code:<15} | {course.section:<8} | {course.term:<10} | {course.enrolled:<10} | {course.capacity:<10}")
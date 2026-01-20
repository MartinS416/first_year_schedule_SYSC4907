from .utils import expand_course, slots_conflict

# Returns True if there is a conflict between two courses
def course_conflict(course_a, course_b) -> bool:
    slots_a = expand_course(course_a)
    slots_b = expand_course(course_b)

    return slots_conflict(slots_a, slots_b)

# Returns True if any course in the group conflicts with any course in the term
def group_conflicts_with_term(course_group, term_courses):
    """
    course_group: list[Course]
    term_courses: list[list[Course]]
    """
    for new_course in course_group:
        new_slots = expand_course(new_course)

        for existing_group in term_courses:
            for existing_course in existing_group:
                existing_slots = expand_course(existing_course)

                if slots_conflict(new_slots, existing_slots):
                    return True
    
    return False

# Returns True if the course group can be added to the term without conflicts
def can_add_group_to_term(course_group, term_courses):
    return not group_conflicts_with_term(course_group, term_courses)
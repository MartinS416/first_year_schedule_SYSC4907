"""
schedule_service.py
-------------------
Business-logic layer for the Schedule Builder.
Views should import from here instead of containing DB logic directly.
"""

from __future__ import annotations

from typing import Any

from ..models import Block, Course, Program, ProgramCourse, Term, TermCourses


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _course_to_dict(course: Course) -> dict[str, Any]:
    """Serialise a Course ORM object to the canonical JSON shape used by the UI."""
    return {
        "code":        course.course_code,
        "section":     course.section,
        "type":        course.instr_type or "",
        "days":        course.days or "",
        "start_time":  str(course.start_time) if course.start_time else "",
        "end_time":    str(course.end_time)   if course.end_time   else "",
        "enrolled":    course.enrolled,
        "capacity":    course.capacity,
    }


def _format_time(time_str: str | None) -> str:
    """Format '0835' → '08:35'. Safe for None / short strings."""
    if not time_str or len(str(time_str)) < 3:
        return ""
    t = str(time_str)
    if len(t) == 3:
        t = "0" + t
    return f"{t[:2]}:{t[2:]}"


def _ranking_class(score: int | float) -> str:
    """Map a numeric ranking to a CSS class name."""
    if score >= 85:
        return "excellent"
    elif score >= 70:
        return "good"
    elif score >= 50:
        return "fair"
    return "poor"


# ---------------------------------------------------------------------------
# Public helpers re-exported for the rest of views.py (unchanged callers)
# ---------------------------------------------------------------------------

format_time   = _format_time
ranking_class = _ranking_class


# ---------------------------------------------------------------------------
# Term course queries
# ---------------------------------------------------------------------------

def get_term_courses_json(term: Term) -> list[dict[str, Any]]:
    """
    Return a JSON-serialisable list of course dicts for a term.
    Used by api_program_data, api_block_timetable, and the schedule builder.
    """
    entries = TermCourses.objects.filter(term=term).select_related()
    seen: set[tuple[str, str]] = set()
    courses: list[dict[str, Any]] = []

    for entry in entries:
        key = (entry.course_code, entry.section)
        if key in seen:
            continue
        seen.add(key)

        try:
            course = Course.objects.get(
                course_code=entry.course_code,
                section=entry.section,
            )
            courses.append(_course_to_dict(course))
        except Course.DoesNotExist:
            continue

    return courses


def get_term_courses_table(
    term: Term, program: Program
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Return (courses_table, missing_codes) for the program-detail page.
    courses_table includes enrollment info; missing_codes are required but
    not yet scheduled.
    """
    entries = TermCourses.objects.filter(term=term)
    courses: list[dict[str, Any]] = []
    scheduled_codes: set[str] = set()

    for entry in entries:
        scheduled_codes.add(entry.course_code)
        try:
            course = Course.objects.get(
                course_code=entry.course_code,
                section=entry.section,
            )
            pct = 0
            if course.capacity and course.capacity > 0:
                pct = round((course.enrolled / course.capacity) * 100)

            if pct >= 95:
                enrollment_status = "full"
            elif pct >= 75:
                enrollment_status = "warn"
            else:
                enrollment_status = "ok"

            courses.append(
                {
                    "code":              course.course_code,
                    "section":           course.section,
                    "type":              course.instr_type or "N/A",
                    "days":              course.days or "N/A",
                    "start_time":        _format_time(course.start_time),
                    "end_time":          _format_time(course.end_time),
                    "enrolled":          course.enrolled,
                    "capacity":          course.capacity or "?",
                    "enrollment_pct":    min(pct, 100),
                    "enrollment_status": enrollment_status,
                }
            )
        except Course.DoesNotExist:
            courses.append(
                {
                    "code":              entry.course_code,
                    "section":          entry.section,
                    "type":              "?",
                    "days":              "?",
                    "start_time":        "",
                    "end_time":          "",
                    "enrolled":          0,
                    "capacity":          "?",
                    "enrollment_pct":    0,
                    "enrollment_status": "ok",
                }
            )

    # Required but not scheduled
    required_codes = set(
        ProgramCourse.objects.filter(program=program, term=term.term_name)
        .exclude(course_code__icontains="Elective")
        .values_list("course_code", flat=True)
    )
    missing = sorted(required_codes - scheduled_codes)

    return courses, missing


# ---------------------------------------------------------------------------
# Program requirements
# ---------------------------------------------------------------------------

def get_program_requirements(program: Program) -> dict[str, list[str]]:
    """
    Return {"fall": [...], "winter": [...]} course code lists for a program.
    """
    fall = list(
        ProgramCourse.objects.filter(program=program, term="fall")
        .values_list("course_code", flat=True)
        .order_by("course_code")
    )
    winter = list(
        ProgramCourse.objects.filter(program=program, term="winter")
        .values_list("course_code", flat=True)
        .order_by("course_code")
    )
    return {"fall": fall, "winter": winter}


# ---------------------------------------------------------------------------
# Course-sections lookup
# ---------------------------------------------------------------------------

def get_course_sections(
    code: str, search_all: bool = False
) -> list[dict[str, Any]]:
    """
    Return section dicts for the given course code.
    If search_all is True, does a case-insensitive contains search.
    """
    if search_all:
        qs = Course.objects.filter(course_code__icontains=code)
    else:
        qs = Course.objects.filter(course_code__iexact=code)

    qs = qs.select_related("parent").order_by("instr_type", "section")

    return [
        {
            "code":           c.course_code,
            "section":        c.section,
            "type":           c.instr_type or "",
            "days":           c.days or "",
            "start_time":     str(c.start_time) if c.start_time else "",
            "end_time":       str(c.end_time)   if c.end_time   else "",
            "enrolled":       c.enrolled,
            "capacity":       c.capacity,
            "parent_section": c.parent.section if c.parent else None,
        }
        for c in qs
    ]


# ---------------------------------------------------------------------------
# Save schedule — full replace strategy with enrollment tracking
# ---------------------------------------------------------------------------

def apply_term_schedule(
    term: Term,
    current_courses: list[dict[str, str]],
) -> dict[str, int]:
    """
    Fully replace the TermCourses for *term* with *current_courses*, and
    update Course.enrolled to reflect the block's student count being added
    or removed from each section.

    current_courses is the complete intended state from the frontend:
        [{"course_code": "MATH 1004", "section": "A"}, ...]

    Returns a dict of {"course_code|section": new_enrolled} for every
    section whose enrollment changed, so the frontend can refresh its
    local cache without a round-trip.

    The entire operation runs inside a single atomic transaction so a
    partial failure cannot leave enrollments in an inconsistent state.
    """
    from django.db import transaction
    from django.db.models import F, Q

    block_size: int = term.block.size or 0

    incoming = {
        (row["course_code"], row["section"])
        for row in current_courses
    }

    with transaction.atomic():
        # ── Compute diff against current DB state ─────────────────────────
        existing_keys = set(
            TermCourses.objects.filter(term=term)
            .values_list("course_code", "section")
        )

        to_remove = existing_keys - incoming   # in DB, not in new state
        to_add    = incoming - existing_keys   # in new state, not in DB

        # ── Remove rows and decrement enrollment ──────────────────────────
        for course_code, section in to_remove:
            TermCourses.objects.filter(
                term=term,
                course_code=course_code,
                section=section,
            ).delete()

            if block_size > 0:
                Course.objects.filter(
                    course_code=course_code,
                    section=section,
                ).update(enrolled=F("enrolled") - block_size)
                # Clamp: negative enrollment is never valid
                Course.objects.filter(
                    course_code=course_code,
                    section=section,
                    enrolled__lt=0,
                ).update(enrolled=0)

        # ── Add rows and increment enrollment ─────────────────────────────
        for course_code, section in to_add:
            TermCourses.objects.create(
                term=term,
                course_code=course_code,
                section=section,
            )

            if block_size > 0:
                Course.objects.filter(
                    course_code=course_code,
                    section=section,
                ).update(enrolled=F("enrolled") + block_size)

        # ── Return updated enrollment numbers for changed sections ─────────
        updated_enrollments: dict[str, int] = {}
        changed_keys = to_remove | to_add

        if changed_keys:
            q = Q()
            for course_code, section in changed_keys:
                q |= Q(course_code=course_code, section=section)

            for row in Course.objects.filter(q).values("course_code", "section", "enrolled"):
                key = f"{row['course_code']}|{row['section']}"
                updated_enrollments[key] = row["enrolled"]

    return updated_enrollments


# ---------------------------------------------------------------------------
# Program data snapshot (for api_program_data)
# ---------------------------------------------------------------------------

def get_program_data_json(program: Program) -> dict[str, Any]:
    """
    Build the full program → blocks → terms → courses payload
    consumed by the schedule builder frontend.
    """
    blocks = Block.objects.filter(program=program).order_by("block_name")

    blocks_out = []
    for block in blocks:
        terms_out = []
        for term in Term.objects.filter(block=block).order_by("term_name"):
            terms_out.append(
                {
                    "id":      term.id,
                    "name":    term.term_name,
                    "courses": get_term_courses_json(term),
                }
            )
        blocks_out.append(
            {
                "id":      block.id,
                "name":    block.block_name,
                "ranking": block.ranking,
                "size":    block.size,
                "terms":   terms_out,
            }
        )

    return {
        "program": {
            "id":       program.id,
            "name":     program.program_name,
            "enrolled": program.enrolled,
        },
        "blocks": blocks_out,
    }
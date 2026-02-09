import io
import json
from contextlib import redirect_stdout

from django.db.models import Avg, Max, Min, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import (
    Block,
    Course,
    Program,
    ProgramCourse,
    Term,
    TermCourses,
)

# ---------------------------------------------------------------------------
#  Context Processor Helper — sidebar programs available on every page
# ---------------------------------------------------------------------------


def _base_context(active_page="", active_program_id=None):
    """Return context dict with sidebar programs and active page marker."""
    programs = Program.objects.all().order_by("program_name")
    return {
        "sidebar_programs": programs,
        "active_page": active_page,
        "active_program_id": active_program_id,
    }


def _format_time(time_str):
    """Format a time string like '0835' into '08:35'."""
    if not time_str or len(str(time_str)) < 3:
        return ""
    t = str(time_str)
    if len(t) == 3:
        t = "0" + t
    return f"{t[:2]}:{t[2:]}"


def _ranking_class(score):
    """Return a CSS class string based on the ranking score."""
    if score >= 85:
        return "excellent"
    elif score >= 70:
        return "good"
    elif score >= 50:
        return "fair"
    else:
        return "poor"


def _get_block_courses_json(term):
    """
    Build a list of course dicts for timetable rendering from a Term object.
    Returns a JSON-serializable list.
    """
    entries = TermCourses.objects.filter(term=term)
    courses_data = []
    seen = set()

    for entry in entries:
        key = (entry.course_code, entry.section)
        if key in seen:
            continue
        seen.add(key)

        try:
            course = Course.objects.get(
                course_code=entry.course_code, section=entry.section
            )
            courses_data.append(
                {
                    "code": course.course_code,
                    "section": course.section,
                    "type": course.instr_type or "",
                    "days": course.days or "",
                    "start_time": str(course.start_time) if course.start_time else "",
                    "end_time": str(course.end_time) if course.end_time else "",
                    "enrolled": course.enrolled,
                    "capacity": course.capacity,
                }
            )
        except Course.DoesNotExist:
            continue

    return courses_data


def _get_block_courses_table(term, program):
    """
    Build data for the course list table within a block, including missing course detection.
    """
    entries = TermCourses.objects.filter(term=term)
    courses = []
    scheduled_codes = set()

    for entry in entries:
        scheduled_codes.add(entry.course_code)
        try:
            course = Course.objects.get(
                course_code=entry.course_code, section=entry.section
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
                    "code": course.course_code,
                    "section": course.section,
                    "type": course.instr_type or "N/A",
                    "days": course.days or "N/A",
                    "start_time": _format_time(course.start_time),
                    "end_time": _format_time(course.end_time),
                    "enrolled": course.enrolled,
                    "capacity": course.capacity or "?",
                    "enrollment_pct": min(pct, 100),
                    "enrollment_status": enrollment_status,
                }
            )
        except Course.DoesNotExist:
            courses.append(
                {
                    "code": entry.course_code,
                    "section": entry.section,
                    "type": "?",
                    "days": "?",
                    "start_time": "",
                    "end_time": "",
                    "enrolled": 0,
                    "capacity": "?",
                    "enrollment_pct": 0,
                    "enrollment_status": "ok",
                }
            )

    # Detect missing courses
    required_codes = set(
        ProgramCourse.objects.filter(program=program, term=term.term_name)
        .exclude(course_code__icontains="Elective")
        .values_list("course_code", flat=True)
    )
    missing = sorted(required_codes - scheduled_codes)

    return courses, missing


# ============================================================================
#  PAGE VIEWS
# ============================================================================


@ensure_csrf_cookie
def dashboard(request):
    """Main dashboard — overview of all programs with summary stats."""
    ctx = _base_context(active_page="dashboard")

    programs = Program.objects.all().order_by("program_name")

    program_data = []
    total_enrolled = 0
    total_blocks = 0
    total_courses_scheduled = 0

    color_palette = [
        "#818cf8",
        "#34d399",
        "#f472b6",
        "#fbbf24",
        "#60a5fa",
        "#a78bfa",
        "#f87171",
        "#2dd4bf",
        "#fb923c",
        "#c084fc",
        "#38bdf8",
        "#4ade80",
        "#e879f9",
        "#facc15",
    ]

    for i, program in enumerate(programs):
        blocks = Block.objects.filter(program=program)
        block_count = blocks.count()
        avg_ranking = blocks.aggregate(avg=Avg("ranking"))["avg"] or 0

        # Count total scheduled course entries across all blocks/terms
        term_ids = Term.objects.filter(block__in=blocks).values_list("id", flat=True)
        scheduled_count = TermCourses.objects.filter(term_id__in=term_ids).count()

        total_enrolled += program.enrolled or 0
        total_blocks += block_count
        total_courses_scheduled += scheduled_count

        program_data.append(
            {
                "program": program,
                "block_count": block_count,
                "avg_ranking": round(avg_ranking),
                "ranking_class": _ranking_class(round(avg_ranking)),
                "scheduled_count": scheduled_count,
                "color": color_palette[i % len(color_palette)],
            }
        )

    total_programs = programs.count()
    unique_courses = Course.objects.values("course_code").distinct().count()

    ctx.update(
        {
            "program_data": program_data,
            "total_programs": total_programs,
            "total_enrolled": total_enrolled,
            "total_blocks": total_blocks,
            "total_courses_scheduled": total_courses_scheduled,
            "unique_courses": unique_courses,
        }
    )

    return render(request, "dashboard.html", ctx)


@ensure_csrf_cookie
def program_detail(request, program_id):
    """Detail view for a single program showing all blocks and their schedules."""
    program = get_object_or_404(Program, pk=program_id)
    ctx = _base_context(active_page="program", active_program_id=program.id)

    blocks = Block.objects.filter(program=program).order_by("block_name")

    blocks_data = []
    terms_available = set()

    for block in blocks:
        terms = Term.objects.filter(block=block).order_by("term_name")

        block_terms = []
        for term in terms:
            terms_available.add(term.term_name)

            courses_table, missing = _get_block_courses_table(term, program)
            courses_json = _get_block_courses_json(term)

            block_terms.append(
                {
                    "term": term,
                    "courses_table": courses_table,
                    "courses_json": json.dumps(courses_json),
                    "missing": missing,
                }
            )

        blocks_data.append(
            {
                "block": block,
                "ranking_class": _ranking_class(block.ranking or 0),
                "terms": block_terms,
            }
        )

    # Required courses for this program
    fall_reqs = list(
        ProgramCourse.objects.filter(program=program, term="fall").values_list(
            "course_code", flat=True
        )
    )
    winter_reqs = list(
        ProgramCourse.objects.filter(program=program, term="winter").values_list(
            "course_code", flat=True
        )
    )

    ctx.update(
        {
            "program": program,
            "blocks_data": blocks_data,
            "terms_available": sorted(terms_available),
            "fall_reqs": fall_reqs,
            "winter_reqs": winter_reqs,
        }
    )

    return render(request, "program_detail.html", ctx)


@ensure_csrf_cookie
def rankings(request):
    """Rankings page — show all blocks sorted by ranking score."""
    ctx = _base_context(active_page="rankings")

    blocks = (
        Block.objects.select_related("program")
        .all()
        .order_by("-ranking", "program__program_name", "block_name")
    )

    blocks_data = []
    for block in blocks:
        blocks_data.append(
            {
                "block": block,
                "program_name": block.program.program_name,
                "ranking_class": _ranking_class(block.ranking or 0),
            }
        )

    # Summary statistics
    total_blocks = blocks.count()
    if total_blocks > 0:
        avg_score = blocks.aggregate(avg=Avg("ranking"))["avg"] or 0
        min_score = blocks.aggregate(m=Min("ranking"))["m"] or 0
        max_score = blocks.aggregate(m=Max("ranking"))["m"] or 0
        excellent_count = blocks.filter(ranking__gte=85).count()
        good_count = blocks.filter(ranking__gte=70, ranking__lt=85).count()
        fair_count = blocks.filter(ranking__gte=50, ranking__lt=70).count()
        poor_count = blocks.filter(ranking__lt=50).count()
    else:
        avg_score = min_score = max_score = 0
        excellent_count = good_count = fair_count = poor_count = 0

    ctx.update(
        {
            "blocks_data": blocks_data,
            "total_blocks": total_blocks,
            "avg_score": round(avg_score),
            "min_score": min_score,
            "max_score": max_score,
            "excellent_count": excellent_count,
            "good_count": good_count,
            "fair_count": fair_count,
            "poor_count": poor_count,
        }
    )

    return render(request, "rankings.html", ctx)


@ensure_csrf_cookie
def generate_page(request):
    """Generate & Rank page — UI for triggering schedule generation and ranking."""
    ctx = _base_context(active_page="generate")

    total_programs = Program.objects.count()
    total_blocks = Block.objects.count()
    total_scheduled = TermCourses.objects.count()
    has_schedule = total_scheduled > 0

    ctx.update(
        {
            "total_programs": total_programs,
            "total_blocks": total_blocks,
            "total_scheduled": total_scheduled,
            "has_schedule": has_schedule,
        }
    )

    return render(request, "generate.html", ctx)


# ============================================================================
#  API ENDPOINTS (AJAX)
# ============================================================================


@require_POST
def api_generate_schedule(request):
    """
    Trigger schedule generation via AJAX. Returns JSON with success status and log output.
    """
    try:
        from .services.schedule_builder import ScheduleBuilder

        # Capture stdout to return as log
        log_buffer = io.StringIO()

        with redirect_stdout(log_buffer):
            builder = ScheduleBuilder()
            builder.generate_schedule()
            builder.export_schedule_to_txt()
            builder.export_visual_grid()

        log_output = log_buffer.getvalue()

        return JsonResponse(
            {
                "success": True,
                "log": log_output,
                "message": "Schedule generated successfully.",
            }
        )

    except Exception as e:
        return JsonResponse(
            {
                "success": False,
                "error": str(e),
                "log": f"ERROR: {str(e)}\n",
            },
            status=500,
        )


@require_POST
def api_rank_blocks(request):
    """
    Trigger block ranking via AJAX. Returns JSON with success status.
    """
    try:
        from .services.ranking import ScheduleRanker

        log_buffer = io.StringIO()

        with redirect_stdout(log_buffer):
            ranker = ScheduleRanker()
            ranker.rank_all_blocks()
            ranker.export_ranking_report()

        log_output = log_buffer.getvalue()

        return JsonResponse(
            {
                "success": True,
                "log": log_output,
                "message": "Ranking complete.",
            }
        )

    except Exception as e:
        return JsonResponse(
            {
                "success": False,
                "error": str(e),
            },
            status=500,
        )


@require_GET
def api_program_data(request, program_id):
    """
    Return JSON data for a program (blocks, terms, courses) for AJAX consumption.
    """
    program = get_object_or_404(Program, pk=program_id)
    blocks = Block.objects.filter(program=program).order_by("block_name")

    data = {
        "program": {
            "id": program.id,
            "name": program.program_name,
            "enrolled": program.enrolled,
        },
        "blocks": [],
    }

    for block in blocks:
        block_info = {
            "id": block.id,
            "name": block.block_name,
            "ranking": block.ranking,
            "size": block.size,
            "terms": [],
        }

        terms = Term.objects.filter(block=block).order_by("term_name")
        for term in terms:
            courses = _get_block_courses_json(term)
            block_info["terms"].append(
                {
                    "id": term.id,
                    "name": term.term_name,
                    "courses": courses,
                }
            )

        data["blocks"].append(block_info)

    return JsonResponse(data)


@require_GET
def api_block_timetable(request, block_id):
    """
    Return JSON timetable data for a specific block (all terms).
    """
    block = get_object_or_404(Block, pk=block_id)
    terms = Term.objects.filter(block=block).order_by("term_name")

    data = {
        "block": {
            "id": block.id,
            "name": block.block_name,
            "program": block.program.program_name,
            "ranking": block.ranking,
            "size": block.size,
        },
        "terms": [],
    }

    for term in terms:
        courses = _get_block_courses_json(term)
        data["terms"].append(
            {
                "id": term.id,
                "name": term.term_name,
                "courses": courses,
            }
        )

    return JsonResponse(data)


@require_GET
def api_rankings_data(request):
    """
    Return JSON of all block rankings.
    """
    blocks = Block.objects.select_related("program").all().order_by("-ranking")

    data = []
    for block in blocks:
        data.append(
            {
                "id": block.id,
                "block_name": block.block_name,
                "program_name": block.program.program_name,
                "ranking": block.ranking,
                "size": block.size,
            }
        )

    return JsonResponse({"rankings": data})


@require_GET
def api_stats(request):
    """
    Return JSON summary statistics for the dashboard.
    """
    total_programs = Program.objects.count()
    total_enrolled = Program.objects.aggregate(s=Sum("enrolled"))["s"] or 0
    total_blocks = Block.objects.count()
    total_scheduled = TermCourses.objects.count()
    unique_courses = Course.objects.values("course_code").distinct().count()
    avg_ranking = Block.objects.aggregate(avg=Avg("ranking"))["avg"] or 0

    return JsonResponse(
        {
            "total_programs": total_programs,
            "total_enrolled": total_enrolled,
            "total_blocks": total_blocks,
            "total_scheduled": total_scheduled,
            "unique_courses": unique_courses,
            "avg_ranking": round(avg_ranking),
        }
    )

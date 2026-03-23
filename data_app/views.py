"""
views.py
--------
Thin controller layer.  All schedule business logic lives in schedule_service.py.
"""

import io
import json
from contextlib import redirect_stdout

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Max, Min, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import Block, Course, Program, ProgramCourse, Term, TermCourses
from .services.schedule_service import (
    apply_term_schedule,
    get_course_sections,
    get_program_data_json,
    get_program_requirements,
    get_term_courses_json,
    get_term_courses_table,
    ranking_class,
)
from .services.log_service import log_error, log_info, log_success


# ---------------------------------------------------------------------------
#  Shared helpers
# ---------------------------------------------------------------------------

def _base_context(active_page: str = "", active_program_id=None) -> dict:
    """Return context dict with sidebar programs and active-page marker."""
    return {
        "sidebar_programs": Program.objects.all().order_by("program_name"),
        "active_page": active_page,
        "active_program_id": active_program_id,
    }


def _json_404(model, **kwargs):
    """get_object_or_404 equivalent that returns a JsonResponse on miss."""
    try:
        return model.objects.get(**kwargs)
    except model.DoesNotExist:
        return JsonResponse({"error": f"{model.__name__} not found."}, status=404)


# ============================================================================
#  Page views
# ============================================================================

@login_required
def admin_home(request):
    return render(request, "admin/home.html")


@ensure_csrf_cookie
def dashboard(request):
    ctx = _base_context(active_page="dashboard")

    programs = Program.objects.all().order_by("program_name")
    color_palette = [
        "#818cf8", "#34d399", "#f472b6", "#fbbf24", "#60a5fa",
        "#a78bfa", "#f87171", "#2dd4bf", "#fb923c", "#c084fc",
        "#38bdf8", "#4ade80", "#e879f9", "#facc15",
    ]

    program_data = []
    total_enrolled = total_blocks = total_courses_scheduled = 0

    for i, program in enumerate(programs):
        blocks = Block.objects.filter(program=program)
        block_count = blocks.count()
        avg_ranking = blocks.aggregate(avg=Avg("ranking"))["avg"] or 0
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
                "ranking_class": ranking_class(round(avg_ranking)),
                "scheduled_count": scheduled_count,
                "color": color_palette[i % len(color_palette)],
            }
        )

    ctx.update(
        {
            "program_data": program_data,
            "total_programs": programs.count(),
            "total_enrolled": total_enrolled,
            "total_blocks": total_blocks,
            "total_courses_scheduled": total_courses_scheduled,
            "unique_courses": Course.objects.values("course_code").distinct().count(),
        }
    )
    return render(request, "dashboard.html", ctx)


@ensure_csrf_cookie
def program_detail(request, program_id):
    program = get_object_or_404(Program, pk=program_id)
    ctx = _base_context(active_page="program", active_program_id=program.id)

    blocks = Block.objects.filter(program=program).order_by("block_name")
    blocks_data = []
    terms_available: set[str] = set()

    for block in blocks:
        block_terms = []
        for term in Term.objects.filter(block=block).order_by("term_name"):
            terms_available.add(term.term_name)
            courses_table, missing = get_term_courses_table(term, program)
            block_terms.append(
                {
                    "term": term,
                    "courses_table": courses_table,
                    "courses_json": json.dumps(get_term_courses_json(term)),
                    "missing": missing,
                }
            )
        blocks_data.append(
            {
                "block": block,
                "ranking_class": ranking_class(block.ranking or 0),
                "terms": block_terms,
            }
        )

    reqs = get_program_requirements(program)
    ctx.update(
        {
            "program": program,
            "blocks_data": blocks_data,
            "terms_available": sorted(terms_available),
            "fall_reqs": reqs["fall"],
            "winter_reqs": reqs["winter"],
        }
    )
    return render(request, "program_detail.html", ctx)


@ensure_csrf_cookie
def rankings(request):
    ctx = _base_context(active_page="rankings")
    blocks = (
        Block.objects.select_related("program")
        .all()
        .order_by("-ranking", "program__program_name", "block_name")
    )

    blocks_data = [
        {
            "block": b,
            "program_name": b.program.program_name,
            "ranking_class": ranking_class(b.ranking or 0),
        }
        for b in blocks
    ]

    total_blocks = blocks.count()
    if total_blocks > 0:
        agg = blocks.aggregate(
            avg=Avg("ranking"), mn=Min("ranking"), mx=Max("ranking")
        )
        avg_score = agg["avg"] or 0
        min_score = agg["mn"] or 0
        max_score = agg["mx"] or 0
        excellent_count = blocks.filter(ranking__gte=85).count()
        good_count      = blocks.filter(ranking__gte=70, ranking__lt=85).count()
        fair_count      = blocks.filter(ranking__gte=50, ranking__lt=70).count()
        poor_count      = blocks.filter(ranking__lt=50).count()
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
    ctx = _base_context(active_page="generate")
    total_scheduled = TermCourses.objects.count()
    ctx.update(
        {
            "total_programs": Program.objects.count(),
            "total_blocks": Block.objects.count(),
            "total_scheduled": total_scheduled,
            "has_schedule": total_scheduled > 0,
        }
    )
    return render(request, "generate.html", ctx)


@ensure_csrf_cookie
def schedules_page(request):
    """Schedule builder page shell — all data loaded via AJAX."""
    ctx = _base_context(active_page="schedules")
    return render(request, "admin/schedules.html", ctx)


# ============================================================================
#  API endpoints
# ============================================================================

@require_POST
def api_generate_schedule(request):
    """
    Trigger schedule generation via AJAX. Returns JSON with success status and log output.
    """
    log_info(
        "Schedule Generation Started", details="User triggered schedule generation."
    )

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

        log_success("Schedule Generation Completed", details=log_output)

        return JsonResponse(
            {
                "success": True,
                "log": log_output,
                "message": "Schedule generated successfully.",
            }
        )

    except Exception as e:
        log_error("Schedule Generation Failed", details=f"Error: {str(e)}")

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
    Standalone rank-only endpoint, streaming SSE.
    Accepts optional flat JSON ranking config body.
    """
    log_info("Block Ranking Started", details="User triggered block ranking.")

    try:
        from .services.ranking import ScheduleRanker

        log_buffer = io.StringIO()

        with redirect_stdout(log_buffer):
            ranker = ScheduleRanker()
            ranker.rank_all_blocks()
            ranker.export_ranking_report()

        log_output = log_buffer.getvalue()

        log_success("Block Ranking Completed", details=log_output)

        return JsonResponse(
            {
                "success": True,
                "log": log_output,
                "message": "Ranking complete.",
            }
        )

    except Exception as e:
        log_error("Block Ranking Failed", details=f"Error: {str(e)}")

        return JsonResponse(
            {
                "success": False,
                "error": str(e),
            },
            status=500,
        )


@require_GET
def api_program_data(request, program_id):
    """Full program → blocks → terms → courses snapshot."""
    program = get_object_or_404(Program, pk=program_id)
    return JsonResponse(get_program_data_json(program))


@require_GET
def api_block_timetable(request, block_id):
    block = get_object_or_404(Block, pk=block_id)
    terms_data = [
        {
            "id": t.id,
            "name": t.term_name,
            "courses": get_term_courses_json(t),
        }
        for t in Term.objects.filter(block=block).order_by("term_name")
    ]
    return JsonResponse(
        {
            "block": {
                "id": block.id,
                "name": block.block_name,
                "program": block.program.program_name,
                "ranking": block.ranking,
                "size": block.size,
            },
            "terms": terms_data,
        }
    )


@require_GET
def api_rankings_data(request):
    blocks = Block.objects.select_related("program").all().order_by("-ranking")
    return JsonResponse(
        {
            "rankings": [
                {
                    "id": b.id,
                    "block_name": b.block_name,
                    "program_name": b.program.program_name,
                    "ranking": b.ranking,
                    "size": b.size,
                }
                for b in blocks
            ]
        }
    )


@require_GET
def api_stats(request):
    return JsonResponse(
        {
            "total_programs":  Program.objects.count(),
            "total_enrolled":  Program.objects.aggregate(s=Sum("enrolled"))["s"] or 0,
            "total_blocks":    Block.objects.count(),
            "total_scheduled": TermCourses.objects.count(),
            "unique_courses":  Course.objects.values("course_code").distinct().count(),
            "avg_ranking":     round(Block.objects.aggregate(avg=Avg("ranking"))["avg"] or 0),
        }
    )


# ── Schedule Builder APIs ────────────────────────────────────────────────────

@require_GET
def api_schedule_requirements(request, program_id):
    program = _json_404(Program, pk=program_id)
    if isinstance(program, JsonResponse):
        return program
    return JsonResponse(get_program_requirements(program))


@require_GET
def api_course_sections(request):
    code = request.GET.get("code", "").strip()
    if not code:
        return JsonResponse({"sections": []})
    search_all = request.GET.get("all", "0") == "1"
    return JsonResponse({"sections": get_course_sections(code, search_all)})


@require_POST
def api_update_term(request):
    """
    Save the schedule for a single term.

    Expects JSON body:
        {
            "term_id":         42,
            "current_courses": [{"course_code": "MATH 1004", "section": "A"}, ...]
        }

    Uses a full-replace strategy via schedule_service.apply_term_schedule so
    the save is always idempotent regardless of how many times the user has
    switched views between edits.

    Response:
        {
            "success": true,
            "enrollment_updates": {"MATH 1004|A": 120, "PHYS 1004|B": 95, ...}
        }
    enrollment_updates contains the new enrolled count for every section
    whose enrollment changed — the frontend uses this to refresh its local
    sections cache without a round-trip.
    """
    try:
        body    = json.loads(request.body)
        term_id = body.get("term_id")
        current = body.get("current_courses", [])

        if not term_id:
            return JsonResponse({"success": False, "error": "term_id is required."}, status=400)

        try:
            term = Term.objects.select_related("block").get(pk=term_id)
        except Term.DoesNotExist:
            return JsonResponse({"success": False, "error": "Term not found."}, status=404)

        enrollment_updates = apply_term_schedule(term, current)
        return JsonResponse({"success": True, "enrollment_updates": enrollment_updates})

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Invalid JSON body."}, status=400)
    except Exception as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=500)
from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path
from . import views

urlpatterns = [
    path("login/", LoginView.as_view(template_name="auth/login.html"), name="login"),
    path("logout/", LogoutView.as_view(next_page="/login/"), name="logout"),
    path("dashboard/home/", views.admin_home, name="admin_home"),
    # ---------------------------------------------------------------
    #  Page Views
    # ---------------------------------------------------------------
    path("", views.dashboard, name="dashboard"),
    path(
        "program/<int:program_id>/",
        views.program_detail,
        name="program_detail",
    ),
    path("rankings/", views.rankings, name="rankings"),
    path("generate/", views.generate_page, name="generate"),
    # ---------------------------------------------------------------
    #  API Endpoints (AJAX)
    # ---------------------------------------------------------------
    path(
        "api/generate/",
        views.api_generate_schedule,
        name="api_generate_schedule",
    ),
    path(
        "api/rank/",
        views.api_rank_blocks,
        name="api_rank_blocks",
    ),
    path(
        "api/program/<int:program_id>/",
        views.api_program_data,
        name="api_program_data",
    ),
    path(
        "api/block/<int:block_id>/timetable/",
        views.api_block_timetable,
        name="api_block_timetable",
    ),
    path(
        "api/rankings/",
        views.api_rankings_data,
        name="api_rankings_data",
    ),
    path(
        "api/stats/",
        views.api_stats,
        name="api_stats",
    ),
    path(
        "api/optimize/",
        views.api_optimize_schedule,
        name="api_optimize_schedule",
    ),

    # ── Schedule Builder page ──────────────────────────────────────────
    path(
        "schedules/",
        views.schedules_page,
        name="schedules",
    ),

    # ── Schedule Builder API ───────────────────────────────────────────
    path(
        "api/schedule/requirements/<int:program_id>/",
        views.api_schedule_requirements,
        name="api_schedule_requirements",
    ),
    path(
        "api/schedule/course-sections/",
        views.api_course_sections,
        name="api_course_sections",
    ),
    path(
        "api/schedule/update-term/",
        views.api_update_term,
        name="api_update_term",
    ),
]

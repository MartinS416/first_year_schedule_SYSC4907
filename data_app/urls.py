from django.urls import path

from . import views

urlpatterns = [
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
]

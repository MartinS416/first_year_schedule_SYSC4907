from django.urls import path
from .views_ranking_config import ranking_config_view

urlpatterns = [
    path('ranking-config/', ranking_config_view, name='ranking-config'),
]

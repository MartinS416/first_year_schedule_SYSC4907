from django.urls import path
from .views_algo_comparison import algo_comparison_view

urlpatterns = [
    path('algo-comparison/', algo_comparison_view, name='algo-comparison'),
]

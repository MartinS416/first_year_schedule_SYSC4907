from django.shortcuts import render, redirect
from data_app.models import RankingConfig

def ranking_config_view(request):
    config, _ = RankingConfig.objects.get_or_create(pk=1)
    if request.method == 'POST':
        for field in ['compactness', 'day_balance', 'end_time_preference', 'start_time_preference', 'late_to_early', 'lab_spread', 'days_used']:
            if field in request.POST:
                setattr(config, field, int(request.POST[field]))
        config.save()
        return redirect('ranking-config')
    return render(request, 'ranking_config.html', {'config': config})

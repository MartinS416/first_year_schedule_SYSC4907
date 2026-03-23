from django.shortcuts import render, redirect
from data_app.models import RankingConfig

def ranking_config_view(request):
    config, _ = RankingConfig.objects.get_or_create(pk=1)
    if request.method == 'POST':
        if 'reset_defaults' in request.POST:
            # Fallback defaults from ScheduleRanker
            config.compactness = 80
            config.day_balance = 60
            config.end_time_preference = 50
            config.start_time_preference = 40
            config.late_to_early = 90
            config.lab_spread = 40
            config.days_used = 70
            config.save()
            return redirect('ranking-config')
        else:
            for field in ['compactness', 'day_balance', 'end_time_preference', 'start_time_preference', 'late_to_early', 'lab_spread', 'days_used']:
                if field in request.POST:
                    setattr(config, field, int(request.POST[field]))
            config.save()
            return redirect('ranking-config')
    
    from data_app.models import Program
    programs = Program.objects.all().order_by("program_name")
    return render(request, 'ranking_config.html', {
        'config': config,
        'sidebar_programs': programs,
        'active_page': '',  
    })

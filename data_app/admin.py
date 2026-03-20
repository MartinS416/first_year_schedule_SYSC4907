from django.contrib import admin
from .models import Program, Block, Term, Course, ProgramCourse, TermCourses, Student, AdminUser, LogEntry
from .models import RankingConfig

admin.site.register(Program)
admin.site.register(Block)
admin.site.register(Term)
admin.site.register(Course)
admin.site.register(ProgramCourse)
admin.site.register(TermCourses)
admin.site.register(Student)
admin.site.register(AdminUser)
admin.site.register(LogEntry)

@admin.register(RankingConfig)
class RankingConfigAdmin(admin.ModelAdmin):
    list_display = [
        'compactness', 'day_balance', 'end_time_preference', 'start_time_preference',
        'late_to_early', 'lab_spread', 'days_used'
    ]
    # Only allow editing the singleton instance
    def has_add_permission(self, request):
        return not RankingConfig.objects.exists()
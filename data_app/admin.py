from django.contrib import admin
from .models import Program, Block, Term, Course, ProgramCourse, TermCourses, Student, AdminUser, LogEntry

admin.site.register(Program)
admin.site.register(Block)
admin.site.register(Term)
admin.site.register(Course)
admin.site.register(ProgramCourse)
admin.site.register(TermCourses)
admin.site.register(Student)
admin.site.register(AdminUser)
admin.site.register(LogEntry)
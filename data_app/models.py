from django.db import models


class Program(models.Model):
    program_name = models.CharField(max_length=255)
    enrolled = models.IntegerField(null=True, blank=True) 


class Block(models.Model):
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="blocks")
    block_name = models.CharField(max_length=255)
    ranking = models.IntegerField()
    timestamp = models.DateTimeField()


class Term(models.Model):
    block = models.ForeignKey(Block, on_delete=models.CASCADE, related_name="terms")
    term_name = models.CharField(max_length=255)


class Course(models.Model):
    course_code = models.CharField(max_length=255)
    section = models.CharField(max_length=50)
    term = models.CharField(max_length=50)
    instr_type = models.CharField(max_length=50)     # LEC, LAB, TUT, PA
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children"
    )
    days = models.CharField(max_length=50, blank=True, null=True)
    start_time = models.CharField(max_length=50, blank=True, null=True)
    end_time = models.CharField(max_length=50, blank=True, null=True)
    capacity = models.IntegerField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["course_code", "section"]),
        ]


class TermCourses(models.Model):
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name="term_courses")
    course_code = models.CharField(max_length=255)
    section = models.CharField(max_length=50)

    class Meta:
        indexes = [
            models.Index(fields=["term", "course_code", "section"]),
        ]


class ProgramCourse(models.Model):
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="program_courses")
    course_code = models.CharField(max_length=255)
    term = models.CharField(max_length=50)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["program", "course_code"], name="unique_program_course")
        ]


class Student(models.Model):
    student_id = models.IntegerField(unique=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="students")
    block = models.ForeignKey(Block, on_delete=models.CASCADE, related_name="students")


class AdminUser(models.Model):
    email = models.CharField(max_length=255, unique=True)
    password_hash = models.CharField(max_length=255)
    role = models.CharField(max_length=50)   # admin, superadmin, etc.
    created_at = models.CharField(max_length=255, blank=True, null=True)


class LogEntry(models.Model):
    admin = models.ForeignKey(AdminUser, on_delete=models.CASCADE, related_name="logs")
    action = models.CharField(max_length=255)
    details = models.TextField(blank=True, null=True)
    timestamp = models.CharField(max_length=255)
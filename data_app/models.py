from django.db import models

class Course(models.Model):
    course_code = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return self.course_code

class Section(models.Model):
    crn = models.IntegerField(unique=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="sections")
    section_id = models.CharField(max_length=20)
    days = models.CharField(max_length=20)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room_capacity = models.IntegerField()
    enrolled = models.IntegerField()

    def __str__(self):
        return f"{self.course.course_code} - {self.section_id} ({self.crn})"


class Program(models.Model):
    program_id = models.IntegerField(unique=True)
    program_name = models.CharField(max_length=100)

    def __str__(self):
        return self.program_name

class ProgramCourse(models.Model):
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="program_courses")
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    term = models.CharField(max_length=10)

    def __str__(self):
        return f"{self.program.program_name} - {self.course.course_code} ({self.term})"


class Block(models.Model):
    block_id = models.IntegerField(unique=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="blocks")
    capacity = models.IntegerField()
    enrolled = models.IntegerField()
    ranking = models.IntegerField()

    def __str__(self):
        return f"Block {self.block_id} ({self.program.program_name})"

class BlockSection(models.Model):
    block = models.ForeignKey(Block, on_delete=models.CASCADE, related_name="block_sections")
    section = models.ForeignKey(Section, on_delete=models.CASCADE)
    type = models.CharField(max_length=10)

    def __str__(self):
        return f"{self.block} - {self.section} ({self.type})"

class Student(models.Model):
    student_id = models.IntegerField(unique=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="students")
    block_id = models.ManyToManyField(Block, related_name="students")

    def __str__(self):
        return f"Student {self.student_id} ({self.program.program_name})"
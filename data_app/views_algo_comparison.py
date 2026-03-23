from django.shortcuts import render
from data_app.models import Program, Block, Term, TermCourses, Course
from data_app.services.schedule_builder import ScheduleBuilder
from data_app.services.ranking import ScheduleRanker
from django.db import transaction


def algo_comparison_view(request):
    # Pick the first program as an example
    program = Program.objects.order_by('program_name').first()
    if not program:
        return render(request, 'algo_comparison.html', {'error': 'No programs found.'})

    # Prepare results for both algorithms
    greedy_result = None
    optimized_result = None
    greedy_score = None
    optimized_score = None

    def get_block_details(block):
        """
        Returns a dict with block, score, explanation, and schedule (terms and their courses)
        """
        ranker = ScheduleRanker()
        block_score, explanation = ranker._calculate_block_score_and_report(block)
        # Schedule: terms and their courses
        terms = Term.objects.filter(block=block).order_by('term_name')
        term_list = []
        for term in terms:
            term_courses = TermCourses.objects.filter(term=term)
            courses = []
            for tc in term_courses:
                try:
                    c = Course.objects.get(course_code=tc.course_code, section=tc.section)
                except Course.DoesNotExist:
                    c = None
                courses.append({
                    'course_code': tc.course_code,
                    'section': tc.section,
                    'course': c,
                })
            term_list.append({
                'term': term,
                'courses': courses,
            })
        return {
            'block': block,
            'score': block_score,
            'explanation': explanation,
            'terms': term_list,
        }

    # --- GREEDY: True greedy (no ranking) ---
    from data_app.services.pure_greedy_schedule_builder import PureGreedyScheduleBuilder
    with transaction.atomic():
        TermCourses.objects.all().delete()
        Course.objects.update(enrolled=0)
        builder = PureGreedyScheduleBuilder()
        builder.MAX_RETRIES = 1
        builder.MAX_RECURSION_DEPTH = 0
        builder.generate_schedule()
        blocks = Block.objects.filter(program=program).order_by('block_name')
        greedy_result = [get_block_details(block) for block in blocks]
        greedy_score = sum(x['score'] for x in greedy_result) / len(greedy_result) if greedy_result else None
        transaction.set_rollback(True)

    # --- OPTIMIZED: Use default settings ---
    with transaction.atomic():
        TermCourses.objects.all().delete()
        Course.objects.update(enrolled=0)
        builder = ScheduleBuilder()
        builder.generate_schedule()
        blocks = Block.objects.filter(program=program).order_by('block_name')
        optimized_result = [get_block_details(block) for block in blocks]
        optimized_score = sum(x['score'] for x in optimized_result) / len(optimized_result) if optimized_result else None
        transaction.set_rollback(True)

    return render(request, 'algo_comparison.html', {
        'program': program,
        'greedy_result': greedy_result,
        'optimized_result': optimized_result,
        'greedy_score': greedy_score,
        'optimized_score': optimized_score,
    })

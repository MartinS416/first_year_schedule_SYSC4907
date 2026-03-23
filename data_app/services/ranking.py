from django.db import models
from data_app.models import Block, Term, TermCourses, Course, ProgramCourse, Program
import math

DEFAULT_RANKING_CONFIG = {
    "base_score":                100,
    "penalty_per_30min_gap":     2,    # points deducted per 30 min of gap beyond 1 hr
    "penalty_per_30min_sleep":   5,    # points deducted per 30 min of lost overnight rest
    "max_gap_allowed_mins":      60,   # free gap window before penalties start
    "min_overnight_rest_hrs":    12,   # minimum overnight rest before sleep penalty
}

class ScheduleRanker:
    """
    Ranks blocks based on schedule quality (0-100).
    """

    def __init__(self, config=None, progress_callback=None):
        """
        config            — dict of penalty weights (missing keys fall back to DEFAULT_RANKING_CONFIG).
        progress_callback — optional callable(event_type, message, pct).
        """
        cfg = {**DEFAULT_RANKING_CONFIG, **(config or {})}
        self.BASE_SCORE               = int(cfg["base_score"])
        self.PENALTY_PER_30MIN_GAP    = int(cfg["penalty_per_30min_gap"])
        self.PENALTY_PER_30MIN_SLEEP  = int(cfg["penalty_per_30min_sleep"])
        self.MAX_GAP_ALLOWED_MINS     = int(cfg["max_gap_allowed_mins"])
        self.MIN_OVERNIGHT_REST_MINS  = int(cfg["min_overnight_rest_hrs"]) * 60
        self.PENALTY_MISSING_COURSE   = 0   # kept for compatibility, currently unused
        self._progress = progress_callback or (lambda *a, **kw: None)

    def _emit(self, msg, kind="info", pct=None):
        print(msg)
        self._progress(kind, msg, pct)

    def rank_all_blocks(self):
        """
        Calculates scores and saves them to the database.
        """
        blocks = Block.objects.all()
        total  = blocks.count()
        self._emit(f"Ranking {total} blocks...", "info", pct=92)

        for i, block in enumerate(blocks):
            final_score, _ = self._calculate_block_score_and_report(block)
            block.ranking = final_score
            block.save()
            pct = int(92 + (i + 1) / total * 6) if total else 98
            self._emit(
                f"  > Updated {block.block_name} ({block.program.program_name}): {final_score}/100",
                "info", pct=pct
            )

    def export_ranking_report(self, filename="ranking_report.txt"):
        """
        Generates a detailed text file explaining exactly why blocks got their scores.
        """
        self._emit(f"Generating detailed report to {filename}...", "info", pct=98)
        blocks = Block.objects.all().order_by('program__program_name', 'block_name')

        try:
            with open(filename, "w", encoding="utf-8") as f:
                for block in blocks:
                    score, report_lines = self._calculate_block_score_and_report(block)
                    
                    f.write("="*60 + "\n")
                    f.write(f"BLOCK: {block.block_name}  |  PROGRAM: {block.program.program_name}\n")
                    f.write(f"FINAL SCORE: {score} / 100\n")
                    f.write("="*60 + "\n")
                    
                    if not report_lines:
                        f.write("  Perfect Score! No penalties detected.\n")
                    else:
                        for line in report_lines:
                            f.write(f"  {line}\n")
                    
                    f.write("\n\n")
            print("Report generation complete.")
            self._emit("Ranking report written.", "success", pct=99)
            
        except IOError as e:
            self._emit(f"Error writing file: {e}", "error")

    def _calculate_block_score_and_report(self, block):
        """
        Calculates score and aggregates report lines for the entire block.
        Returns: (avg_score, list_of_report_strings)
        """
        terms = Term.objects.filter(block=block)
        if not terms.exists():
            return 0, ["Error: No terms found in block."]

        total_score = 0
        block_report = []

        for term in terms:
            t_score, t_report = self._score_term(term, block.program)
            total_score += t_score
            
            # Add term headers to the report
            if t_report:
                block_report.append(f"--- {term.term_name.upper()} TERM (Score: {t_score}) ---")
                block_report.extend(t_report)
                block_report.append("") # Spacer

        # Average the score
        avg_score = int(total_score / terms.count())
        return avg_score, block_report

    def _score_term(self, term, program):
        """
        Scores a term and returns detailed explanations for deductions.
        """
        current_score = self.BASE_SCORE
        report = []
        
        # 1. Fetch courses
        term_links = TermCourses.objects.filter(term=term)
        courses = []
        scheduled_codes = set()

        for link in term_links:
            scheduled_codes.add(link.course_code)
            try:
                c = Course.objects.get(course_code=link.course_code, section=link.section)
                if c.days and c.start_time and c.end_time:
                    courses.append(c)
            except Course.DoesNotExist:
                continue

        # 2. CHECK MISSING COURSES
        # required_codes = set(
        #     ProgramCourse.objects.filter(program=program, term=term.term_name)
        #     .values_list('course_code', flat=True)
        # )
        
        # missing = required_codes - scheduled_codes
        # if missing:
        #     deduction = len(missing) * self.PENALTY_MISSING_COURSE
        #     current_score -= deduction
            # report.append(f"[-{deduction}] Missing {len(missing)} required courses: {', '.join(missing)}")

        # 3. BUILD GRID
        daily_grid = {0: [], 1: [], 2: [], 3: [], 4: []} # Mon=0, Fri=4
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
        
        for c in courses:
            days_indices = self._parse_days(c.days)
            s_min = self._parse_time(c.start_time)
            e_min = self._parse_time(c.end_time)
            for d in days_indices:
                daily_grid[d].append((s_min, e_min))

        for d in daily_grid:
            daily_grid[d].sort(key=lambda x: x[0])

        # 4. CALCULATE GAPS (with explanation)
        gap_deduction, gap_notes = self._calc_gap_penalty(daily_grid, day_names)
        if gap_deduction > 0:
            current_score -= gap_deduction
            report.extend(gap_notes)

        # 5. CALCULATE SLEEP (with explanation)
        sleep_deduction, sleep_notes = self._calc_sleep_penalty(daily_grid, day_names)
        if sleep_deduction > 0:
            current_score -= sleep_deduction
            report.extend(sleep_notes)

        return current_score, report

    def _calc_gap_penalty(self, daily_grid, day_names):
        penalty = 0
        notes = []
        
        for d, classes in daily_grid.items():
            if len(classes) < 2: continue
            
            for i in range(len(classes) - 1):
                gap_mins = classes[i+1][0] - classes[i][1]
                
                if gap_mins > self.MAX_GAP_ALLOWED_MINS:
                    excess = gap_mins - self.MAX_GAP_ALLOWED_MINS
                    pts = (excess // 30) * self.PENALTY_PER_30MIN_GAP
                    if pts > 0:
                        penalty += pts
                        gap_hrs = round(gap_mins / 60, 1)
                        allowed_hrs = round(self.MAX_GAP_ALLOWED_MINS / 60, 1)
                        notes.append(f"[-{pts}] {day_names[d]}: Large gap of {gap_hrs} hrs (Allowed: {allowed_hrs} hr)")

        return penalty, notes

    def _calc_sleep_penalty(self, daily_grid, day_names):
        penalty = 0
        notes = []
        MIN_REST = self.MIN_OVERNIGHT_REST_MINS
        
        for d in range(4):
            if not daily_grid[d] or not daily_grid[d+1]:
                continue

            last_end    = daily_grid[d][-1][1]
            first_start = daily_grid[d+1][0][0]

            mins_until_midnight = 1440 - last_end
            total_rest = mins_until_midnight + first_start

            if total_rest < MIN_REST:
                lost = MIN_REST - total_rest
                pts = (lost // 30) * self.PENALTY_PER_30MIN_SLEEP
                if pts > 0:
                    penalty += pts
                    rest_hrs     = round(total_rest / 60, 1)
                    req_hrs      = round(MIN_REST / 60, 1)
                    notes.append(f"[-{pts}] {day_names[d]}->{day_names[d+1]}: Only {rest_hrs} hrs rest (Req: {req_hrs} hrs)")
        
        return penalty, notes

    # --- HELPERS ---
    def _parse_days(self, days_str):
        mapping = {'M': 0, 'T': 1, 'W': 2, 'R': 3, 'F': 4}
        return [mapping[c] for c in (days_str or "").upper() if c in mapping]

    def _parse_time(self, time_val):
        try:
            t = str(time_val).zfill(4)
            return int(t[:2]) * 60 + int(t[2:])
        except: return 0
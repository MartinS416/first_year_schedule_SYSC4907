from django.db import models
from data_app.models import Block, Term, TermCourses, Course, ProgramCourse, Program
import math

class ScheduleRanker:
    """
    Ranks blocks based on schedule quality (0-100).
    Now includes detailed reporting capabilities.
    """

    # --- CONFIGURATION WEIGHTS ---

    BASE_SCORE = 100
    # Rule weights (can be tuned)
    WEIGHTS = {
        "compactness": 80,
        "day_balance": 60,
        "end_time_preference": 50,
        "start_time_preference": 40,
        "late_to_early": 90,
        "lab_spread": 40,
        "days_used": 70,
    }

    GAP_CAP = 240  # 4 hours

    def rank_all_blocks(self):
        """
        Calculates scores and saves them to the database.
        Prints a summary to the console.
        """
        blocks = Block.objects.all()
        print(f"Ranking {blocks.count()} blocks...")

        for block in blocks:
            # We only care about the integer score for the DB
            final_score, _ = self._calculate_block_score_and_report(block)
            
            block.ranking = final_score
            block.save()
            print(f"  > Updated {block.block_name} ({block.program.program_name}): {final_score}/100")

    def export_ranking_report(self, filename="ranking_report.txt"):
        """
        Generates a detailed text file explaining exactly why blocks got their scores.
        """
        print(f"Generating detailed report to {filename}...")
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
            
        except IOError as e:
            print(f"Error writing file: {e}")

    def _calculate_block_score_and_report(self, block):
        """
        Calculates score and aggregates report lines for the entire block.
        Returns: (block_score, list_of_report_strings)
        """
        terms = Term.objects.filter(block=block)
        if not terms.exists():
            return 0, ["Error: No terms found in block."]

        term_scores = []
        block_report = []

        for term in terms:
            t_score, t_report = self._score_term(term, block.program)
            term_scores.append(t_score)
            if t_report:
                block_report.append(f"--- {term.term_name.upper()} TERM (Score: {t_score}) ---")
                block_report.extend(t_report)
                block_report.append("")

        # Block score: normalized sum of term scores
        block_score = int(sum(term_scores) / (len(term_scores))) if term_scores else 0
        return block_score, block_report


    def _score_term(self, term, program):
        """
        Scores a term using modular rules and returns explanations.
        """
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

        # 2. Build daily grid
        daily_grid = {0: [], 1: [], 2: [], 3: [], 4: []}
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
        for c in courses:
            days_indices = self._parse_days(c.days)
            s_min = self._parse_time(c.start_time)
            e_min = self._parse_time(c.end_time)
            for d in days_indices:
                daily_grid[d].append((s_min, e_min))
        for d in daily_grid:
            daily_grid[d].sort(key=lambda x: x[0])

        # 3. Modular scoring rules
        scores = {}
        notes = []

        # Compactness (gap minutes)
        total_gap = self._total_gap_minutes(daily_grid)
        scores["compactness"] = 1 - min(total_gap / self.GAP_CAP, 1)
        notes.append(f"[compactness] Total gap minutes: {total_gap}")

        # Days used
        days_used = self._days_used(daily_grid)
        scores["days_used"] = self._days_used_score(days_used)
        notes.append(f"[days_used] Days scheduled: {days_used}")

        # Day balance
        scores["day_balance"] = self._day_balance_score(daily_grid)

        # End time preference (finish earlier)
        scores["end_time_preference"] = self._end_time_preference(daily_grid)

        # Start time preference (start later)
        scores["start_time_preference"] = self._start_time_preference_score(daily_grid)

        # Late-to-early (sleep penalty)
        late_penalty, late_notes = self._calc_late_to_early_penalty(daily_grid, day_names)
        notes.extend(late_notes)
        scores["late_to_early"] = max(0.0, 1 - (late_penalty / 100))

        # Lab spread (stub)
        scores["lab_spread"] = self._lab_spread_score(courses)

        # Weighted sum
        weighted_sum = 0
        weight_total = 0
        for k, w in self.WEIGHTS.items():
            weighted_sum += w * scores.get(k, 1.0)
            weight_total += w

        term_score = int(100 * (weighted_sum / weight_total)) if weight_total else 0
        return term_score, self._format_rule_report(scores, notes)


    # --- Modular rule helpers ---
    def _total_gap_minutes(self, daily_grid):
        total = 0
        for classes in daily_grid.values():
            if len(classes) < 2:
                continue
            for i in range(len(classes) - 1):
                total += max(0, classes[i+1][0] - classes[i][1])
        return total

    def _days_used(self, daily_grid):
        return sum(1 for d in daily_grid if daily_grid[d])

    def _days_used_score(self, days_used, ideal=4, max_days=5):
        if days_used <= ideal:
            return 1.0
        if days_used >= max_days:
            return 0.0
        return 1 - ((days_used - ideal) / (max_days - ideal))

    def _day_balance_score(self, daily_grid):
        active_days = [d for d, classes in daily_grid.items() if classes]
        if not active_days:
            return 1.0
        singleton_days = sum(1 for d in active_days if len(daily_grid[d]) == 1)
        return 1 - (singleton_days / len(active_days))

    def _end_time_preference(self, daily_grid, target_end=1020, max_end=1290):
        """
        Rewards schedules where the latest class ends at or before the preferred time (prefer ending at or before 5 PM).
        Returns 1.0 for ending at or before target_end, 0.0 for ending at or after max_end, linear in between.
        """
        latest_end = 0
        for classes in daily_grid.values():
            if classes:
                latest_end = max(latest_end, classes[-1][1])
        if latest_end <= target_end:
            return 1.0
        if latest_end >= max_end:
            return 0.0
        return 1 - ((latest_end - target_end) / (max_end - target_end))

    def _start_time_preference_score(self, daily_grid, ideal_start=540, max_early=480):
        """
        Rewards schedules where the earliest class starts at or after the preferred time (prefer starting at or after 9 AM).
        Returns 1.0 for starting at or after ideal_start, 0.0 for starting at or before max_early, linear in between.
        """
        earliest_start = min((classes[0][0] for classes in daily_grid.values() if classes), default=1440)
        if earliest_start >= ideal_start:
            return 1.0
        if earliest_start <= max_early:
            return 0.0
        return (earliest_start - max_early) / (ideal_start - max_early)

    def _calc_late_to_early_penalty(self, daily_grid, day_names):
        penalty = 0
        notes = []
        MIN_REST = 12 * 60 # 720 mins
        for d in range(4): # Mon(0) -> Thu(3)
            if not daily_grid[d] or not daily_grid[d+1]:
                continue
            last_end = daily_grid[d][-1][1]
            first_start = daily_grid[d+1][0][0]
            mins_until_midnight = 1440 - last_end
            total_rest = mins_until_midnight + first_start
            if total_rest < MIN_REST:
                lost = MIN_REST - total_rest
                pts = (lost // 30) * 5  # keep penalty scale
                if pts > 0:
                    penalty += pts
                    rest_hrs = round(total_rest / 60, 1)
                    notes.append(f"[late-to-early] Only {rest_hrs} hrs rest {day_names[d]}->{day_names[d+1]} (Req: 12 hrs)")
        return penalty, notes

    def _lab_spread_score(self, courses):
        # Group by course_code, find LEC and LAB/TUT for each
        spreads = []
        course_map = {}
        for c in courses:
            course_map.setdefault(c.course_code, []).append(c)
        for code, comps in course_map.items():
            lecs = [c for c in comps if getattr(c, 'instr_type', None) == "LEC"]
            labs_tuts = [c for c in comps if getattr(c, 'instr_type', None) in ("LAB", "TUT")]
            for lec in lecs:
                lec_days = self._parse_days(getattr(lec, 'days', None))
                for comp in labs_tuts:
                    comp_days = self._parse_days(getattr(comp, 'days', None))
                    if lec_days and comp_days:
                        min_dist = min(abs(ld - cd) for ld in lec_days for cd in comp_days)
                        spreads.append(min_dist)
        if not spreads:
            return 1.0
        avg_spread = sum(spreads) / len(spreads)
        # Normalize: 0 days apart = 1.0, 4 days apart = 0.0
        return 1.0 - min(avg_spread / 4, 1)

    def _format_rule_report(self, scores, notes):
        lines = []
        for rule, s in scores.items():
            lines.append(f"[{rule}] score={round(s, 3)}")
        lines.extend(notes)
        return lines

    # --- HELPERS ---
    def _parse_days(self, days_str):
        mapping = {'M': 0, 'T': 1, 'W': 2, 'R': 3, 'F': 4}
        return [mapping[c] for c in (days_str or "").upper() if c in mapping]

    def _parse_time(self, time_val):
        try:
            t = str(time_val).zfill(4)
            return int(t[:2]) * 60 + int(t[2:])
        except: return 0
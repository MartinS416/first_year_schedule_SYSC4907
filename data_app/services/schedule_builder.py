import math
from django.utils import timezone
from data_app import models
from data_app.models import Course, Program, Block, ProgramCourse, Term, Student, TermCourses
import random
from django.db import models
from .schedule_validator import can_add_group_to_term
from django.db import transaction
from .utils import *

# ---------------------------------------------------------------------------
# Default configuration — matches original hardcoded behaviour exactly
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "block_size":          20,    # students per block
    "max_retries":         1,     # generation attempts before giving up
    "max_recursion_depth": 3,     # kick-and-repair recursion limit
    "enforce_capacity":    True,  # reject sections that are over capacity
    "skip_electives":      True,  # exclude courses with "Elective" in the code
}


class ScheduleBuilder:

    BLOCK_SIZE = 20
    SHARED_COURSES = {}
    
    PRIORITY_COURSES = ["ECOR 1041"]

    def build_blocks(self):
        """
        Creates Block and Term objects based on Program enrollment.
        """
        for program in Program.objects.all():
            self._build_blocks_for_program(program)

    def _build_blocks_for_program(self, program: Program):
        enrolled = program.enrolled or 0

        if enrolled <= 0:
            self._emit(f"Error : Program {program.program_name} has no enrolled students.", "error")
            return
    
        num_blocks = math.ceil(enrolled / self.BLOCK_SIZE)
        
        self._emit(f"Building blocks for program: {program.program_name} with {enrolled} enrolled students.")

        # Delete old blocks
        Block.objects.filter(program=program).delete()

        for i in range(num_blocks):
            block_name = f"Block {chr(ord('A') + i)}"
            
            if i == num_blocks - 1:
                capacity = enrolled - (i * self.BLOCK_SIZE)
            else:
                capacity = self.BLOCK_SIZE

            block = Block.objects.create(
                program=program,
                block_name=block_name,
                ranking=0,
                timestamp=timezone.now(),
                size=capacity
            )

            Term.objects.create(block=block, term_name="fall")
            Term.objects.create(block=block, term_name="winter")
            
        self._emit(f"Created {num_blocks} blocks for program: {program.program_name}", "success")

    def find_shared_courses(self):
        """
        Prioritizes courses by:
        0. Manual Priority Bias (Forces problem courses to the front)
        1. Program Frequency (Constraints)
        2. Flexibility (Fewest sections first)
        3. Random weight (To vary results on retries)
        """
        course_stats = (
            ProgramCourse.objects
            .exclude(course_code__icontains="Elective")
            .values('course_code')
            .annotate(program_count=models.Count('program', distinct=True))
        )
        if self.SKIP_ELECTIVES:
            qs = qs.exclude(course_code__icontains="Elective")

        enriched_stats = []
        for entry in qs:
            code = entry['course_code']
            
            # Get total number of distinct sections (bundles)
            num_bundles = len(self.get_course_bundles(code))

            # --- ADD THIS: Assign a score of 1 if it's in the priority list, else 0 ---
            priority_score = 1 if code in self.PRIORITY_COURSES else 0

            enriched_stats.append({
                'course_code':   code,
                'program_count': entry['program_count'],
                'flexibility': num_bundles, 
                'random_weight': random.random(),
                'priority_score': priority_score   # <--- Add to dictionary
            })
        
        # Sort Logic:
        # 0. Manual Priority (1 goes before 0)
        # 1. Most Programs (Constraints)
        # 2. FEWEST bundles (Flexibility - Low is hard) -> Use negative or reverse sort
        enriched_stats.sort(
            key=lambda x: (
                x['priority_score'],    # <--- Put priority score FIRST in the tuple
                x['program_count'], 
                -x['flexibility'], 
                x['random_weight']
            ),
            reverse=True
        )
        return enriched_stats
    
    @staticmethod
    def _lab_lec_letter(section: str):
        """
        Extract the LEC section letter from a lab section name.

        Pattern A  — L<number><letter>   e.g. 'L1A', 'L2C', 'L1D'
            The trailing letter(s) identify which LEC section this lab belongs to.
            'L1A' → 'A',  'L2C' → 'C'

        Pattern B  — L<number>  e.g. 'L1', 'L2', 'L10'
            No trailing letter → universal lab (attach to every LEC).
            Returns None.

        Anything that doesn't start with L + digit is also treated as universal.
        """
        import re
        m = re.match(r'^[Ll]\d+([A-Za-z]+)$', section.strip())
        if m:
            return m.group(1).upper()   # 'A', 'B', 'C', …
        return None                     # universal

    def get_course_bundles(self, course_code, term_name=None):
        """
        Return a list of all possible [LEC, (LAB), (TUT)] bundles.

        Lab assignment rules
        ───────────────────
        1. If a lab has its parent FK set → use it directly (FK always wins).
        2. If a lab has parent=None:
             Pattern A  (e.g. L1A, L2B): trailing letter = LEC section it belongs to.
                        'L1A' goes to the LEC whose section == 'A'.
             Pattern B  (e.g. L1, L2):   no trailing letter → universal,
                        attach to every LEC.
             Fallback:  if no pattern-A lab can be matched to any known LEC,
                        treat all orphan labs as universal.

        term_name filters to a specific semester ('fall'/'winter') so fall
        LECs are never paired with winter LABs.
        """
        import re

        qs = Course.objects.filter(course_code=course_code)
        if term_name:
            qs = qs.filter(term__iexact=term_name)
        all_sections = list(qs)

        lecs = [c for c in all_sections if c.instr_type == "LEC"]
        all_labs = [c for c in all_sections if c.instr_type == "LAB"]
        all_tuts = [c for c in all_sections if c.instr_type == "TUT"]

        # ── Separate FK-linked children from orphans ───────────────────────
        # For labs
        fk_labs   = [c for c in all_labs if c.parent_id is not None]
        orphan_labs = [c for c in all_labs if c.parent_id is None]

        # For tuts
        fk_tuts     = [c for c in all_tuts if c.parent_id is not None]
        orphan_tuts = [c for c in all_tuts if c.parent_id is None]

        # ── Classify orphan labs ───────────────────────────────────────────
        # pattern_a_labs: { 'A': [lab, lab, …], 'B': […], … }
        # universal_labs: labs that belong to every LEC
        pattern_a_labs = {}
        universal_labs = []

        for lab in orphan_labs:
            letter = self._lab_lec_letter(lab.section)
            if letter:
                pattern_a_labs.setdefault(letter, []).append(lab)
            else:
                universal_labs.append(lab)

        # Same classification for orphan tuts (in case tuts follow the same pattern)
        pattern_a_tuts = {}
        universal_tuts = []

        for tut in orphan_tuts:
            letter = self._lab_lec_letter(tut.section)
            if letter:
                pattern_a_tuts.setdefault(letter, []).append(tut)
            else:
                universal_tuts.append(tut)

        # ── Sanity check: if no pattern-A lab matches any LEC section,
        #    promote them all to universal (handles unexpected naming)
        known_lec_sections = {lec.section.upper() for lec in lecs}
        if pattern_a_labs and not any(
            letter in known_lec_sections for letter in pattern_a_labs
        ):
            universal_labs.extend(
                lab for labs in pattern_a_labs.values() for lab in labs
            )
            pattern_a_labs = {}

        if pattern_a_tuts and not any(
            letter in known_lec_sections for letter in pattern_a_tuts
        ):
            universal_tuts.extend(
                tut for tuts in pattern_a_tuts.values() for tut in tuts
            )
            pattern_a_tuts = {}

        # ── Build bundles per LEC ──────────────────────────────────────────
        bundles = []

        for lec in lecs:
            lec_key = lec.section.upper()

            # Labs for this LEC: FK children + pattern-A matches + universal orphans
            lec_fk_labs = [c for c in fk_labs if c.parent_id == lec.pk]
            lec_pa_labs  = pattern_a_labs.get(lec_key, [])
            lec_labs     = lec_fk_labs + lec_pa_labs + universal_labs

            # Tuts for this LEC: FK children + pattern-A matches + universal orphans
            lec_fk_tuts = [c for c in fk_tuts if c.parent_id == lec.pk]
            lec_pa_tuts  = pattern_a_tuts.get(lec_key, [])
            lec_tuts     = lec_fk_tuts + lec_pa_tuts + universal_tuts

            if not lec_labs and not lec_tuts:
                bundles.append([lec])
                continue

            for lab in (lec_labs or [None]):
                for tut in (lec_tuts or [None]):
                    bundle = [lec]
                    if lab: bundle.append(lab)
                    if tut: bundle.append(tut)
                    bundles.append(bundle)

        return bundles
    
    def generate_schedule(self):
        self._emit(
            f"\n=== STARTING SCHEDULE GENERATION (Max Retries: {self.MAX_RETRIES}) ===",
            "info", pct=0
        )
        
        # 1. Build structure
        self._emit("Step 1/3 — Building blocks…", "info", pct=5)
        self.build_blocks()
        
        if Block.objects.count() == 0:
            self._emit("CRITICAL ERROR: No blocks were created. Check 'Program' table and 'enrolled' count.", "error", pct=100)
            return

        total_blocks = Block.objects.count()

        for attempt in range(1, self.MAX_RETRIES + 1):
            self._emit(f"\n>>> ATTEMPT {attempt} / {self.MAX_RETRIES}", "info",
                       pct=int(10 + (attempt - 1) / self.MAX_RETRIES * 80))

            with transaction.atomic():
                TermCourses.objects.all().delete()
                Course.objects.update(enrolled=0)
            
            # 2. Get courses
            self._emit("Step 2/3 — Prioritising courses…", "info", pct=15)
            sorted_courses = self.find_shared_courses()
            
            if not sorted_courses:
                self._emit("CRITICAL ERROR: No shared courses found. Check 'ProgramCourse' table.", "error", pct=100)
                return

            # 3. Schedule each course, emitting per-course progress
            self._emit("Step 3/3 — Assigning sections to blocks…", "info", pct=20)
            total_courses = len(sorted_courses)
            for idx, course_info in enumerate(sorted_courses):
                course_code = course_info['course_code']
                self._schedule_course_globally(course_code)
                pct = int(20 + (idx + 1) / total_courses * 70)
                self._emit(
                    f"  [{idx+1}/{total_courses}] Scheduled {course_code}",
                    "progress", pct=pct
                )

            missing_count = self._count_missing_courses()
            
            if missing_count == 0:
                self._emit(
                    f"\nSUCCESS: Perfect schedule generated on attempt {attempt}! (all required courses have a LEC assigned)",
                    "success", pct=95
                )
                break
            else:
                self._emit(
                    f"      [!] Attempt {attempt} result: {missing_count} course(s) missing or lacking a LEC section.",
                    "warning"
                )
                if attempt == self.MAX_RETRIES:
                    self._emit(
                        "\nWARNING: Max retries reached. The schedule is incomplete.",
                        "warning", pct=95
                    )

        self._emit("\n=== GENERATION COMPLETE ===", "success", pct=100)

    def _count_missing_courses(self):
        """
        Count required courses that are either completely absent OR present without a LEC.
        A course is only considered "scheduled" if at least one of its assigned sections
        is a LEC (instr_type='LEC').  Having only a LAB/TUT without a LEC is treated
        the same as not being scheduled at all.
        """
        missing_count = 0
        elective_filter = {"course_code__icontains": "Elective"} if self.SKIP_ELECTIVES else {}

        for program in Program.objects.all():
            for block in Block.objects.filter(program=program):
                for term in Term.objects.filter(block=block):
                    required_codes = set(
                        ProgramCourse.objects.filter(program=program, term=term.term_name)
                        .exclude(**elective_filter)
                        .values_list('course_code', flat=True)
                    )

                    # Build set of course codes that have at least one LEC scheduled
                    term_links = TermCourses.objects.filter(term=term)
                    codes_with_lec = set()
                    for link in term_links:
                        try:
                            c = Course.objects.get(
                                course_code=link.course_code,
                                section=link.section
                            )
                            if c.instr_type == "LEC":
                                codes_with_lec.add(link.course_code)
                        except Course.DoesNotExist:
                            continue

                    missing_count += len(required_codes - codes_with_lec)

        return missing_count

    def _schedule_course_globally(self, course_code, depth=0):
        if depth > self.MAX_RECURSION_DEPTH:
            self._emit(f"      [!] Max depth reached. Cannot schedule {course_code}.", "warning")
            return False

        targets = self._get_terms_needing_course(course_code)

        # Only skip a term if it already has a LEC for this course.
        def _has_lec(term):
            for link in TermCourses.objects.filter(term=term, course_code=course_code):
                try:
                    c = Course.objects.get(course_code=link.course_code, section=link.section)
                    if c.instr_type == "LEC":
                        return True
                except Course.DoesNotExist:
                    continue
            return False

        targets = [t for t in targets if not _has_lec(t)]
        random.shuffle(targets)

        for term in targets:
            # Get bundles filtered to this term's season so fall LECs never
            # end up paired with winter LABs (or vice versa).
            bundles = self.get_course_bundles(course_code, term_name=term.term_name)

            if not bundles:
                self._emit(f"      [x] No bundles for {course_code} in {term.term_name}", "warning")
                continue

            success = self._attempt_to_schedule_term(term, course_code, bundles)
            
            if not success and depth < self.MAX_RECURSION_DEPTH:
                success = self._attempt_force_schedule(term, course_code, bundles, depth)

            if not success:
                self._emit(f"      [x] Failed to place {course_code} in {term.term_name}", "warning")

    def _attempt_force_schedule(self, term, new_course_code, new_bundles, depth):
        existing_groups = self._get_existing_course_objects_for_term(term)
        
        # FIX: Get the block size once at the beginning (default to 0 if None)
        block_size = term.block.size or 0
        
        # Sort victims by "Ease of Rescheduling" (Flexibility)
        victim_scores = []
        for group in existing_groups:
            c_code = group[0].course_code
            num_options = len(self.get_course_bundles(c_code, term_name=term.term_name))
            victim_scores.append({'group': group, 'code': c_code, 'score': num_options})
        
        victim_scores.sort(key=lambda x: x['score'], reverse=True)
        random.shuffle(new_bundles)

        for new_bundle in new_bundles:
            # FIX: Ensure the new bundle actually has enough capacity before proceeding!
            if not self._has_capacity(new_bundle, block_size):
                continue
            
            # Iterate through our SORTED list of victims
            for item in victim_scores:
                existing_group = item['group']
                victim_code    = item['code']
                
                if victim_code == new_course_code:
                    continue

                temp_schedule = [g['group'] for g in victim_scores if g['code'] != victim_code]
                
                if can_add_group_to_term(new_bundle, temp_schedule):
                    
                    # 1. Delete Victim and decrement enrollment for SPECIFIC sections
                    print(f"      [!] Kicking out {victim_code} to make room for {new_course_code}...")
                    
                    # Decrement enrollment for each specific course in the victim bundle
                    for course_part in existing_group:
                        Course.objects.filter(pk=course_part.pk).update(
                            enrolled=models.F('enrolled') - block_size
                        )

                    TermCourses.objects.filter(term=term, course_code=victim_code).delete()
                    self._commit_bundle_to_term(term, new_bundle, block_size)
                    self._schedule_course_globally(victim_code, depth=depth + 1)
                    return True

        return False

    def _get_terms_needing_course(self, course_code):
        targets = []
        for req in ProgramCourse.objects.filter(course_code=course_code):
            for block in Block.objects.filter(program=req.program):
                targets.extend(Term.objects.filter(block=block, term_name=req.term))
        return targets

    def _attempt_to_schedule_term(self, term, course_code, bundles):
        block_size = term.block.size or 0
        current_term_courses_objects = self._get_existing_course_objects_for_term(term)
        random.shuffle(bundles)

        for bundle in bundles:
            if not self._has_capacity(bundle, block_size):
                continue
            if not can_add_group_to_term(bundle, current_term_courses_objects):
                continue
            self._commit_bundle_to_term(term, bundle, block_size)
            return True

        return False

    def _get_existing_course_objects_for_term(self, term):
        scheduled_entries = TermCourses.objects.filter(term=term)
        grouped_codes = {}
        for entry in scheduled_entries:
            grouped_codes.setdefault(entry.course_code, []).append(entry.section)

        existing_groups = []
        for code, sections in grouped_codes.items():
            courses = list(Course.objects.filter(course_code=code, section__in=sections))
            if courses:
                existing_groups.append(courses)
        return existing_groups

    def _has_capacity(self, bundle, block_size):
        """
        Check every section in the bundle has room for block_size more students.

        Always reads enrolled directly from the DB — never trusts the in-memory
        value on the Course object, which goes stale the moment any other term
        commits the same shared section.  This is the single authoritative gate;
        no caller needs to pre-refresh the bundle before calling this.
        """
        if not self.ENFORCE_CAPACITY:
            return True

        pks = [c.pk for c in bundle if c.capacity is not None]
        if not pks:
            return True

        fresh = {
            row['id']: row['enrolled']
            for row in Course.objects.filter(pk__in=pks).values('id', 'enrolled')
        }
        for course_part in bundle:
            if course_part.capacity is None:
                continue
            current_enrolled = fresh.get(course_part.pk, course_part.enrolled)
            if (current_enrolled + block_size) > course_part.capacity:
                return False
        return True

    def _commit_bundle_to_term(self, term, bundle, block_size):
        with transaction.atomic():
            for course_part in bundle:
                TermCourses.objects.create(
                    term=term,
                    course_code=course_part.course_code,
                    section=course_part.section,
                )
                Course.objects.filter(pk=course_part.pk).update(
                    enrolled=models.F('enrolled') + block_size
                )
                course_part.enrolled += block_size

    def export_schedule_to_txt(self, filename="generated_schedule.txt"):
        self._emit(f"Exporting schedule to {filename}...")
        try:
            with open(filename, "w", encoding="utf-8") as f:
                programs = Program.objects.all().order_by('program_name')
                
                for program in programs:
                    f.write("="*85 + "\n")
                    f.write(f"PROGRAM: {program.program_name} (Enrolled: {program.enrolled})\n")
                    f.write("="*85 + "\n")

                    blocks = Block.objects.filter(program=program).order_by('block_name')
                    if not blocks.exists():
                        f.write("  No blocks generated.\n")
                        continue

                    for block in blocks:
                        f.write(f"\n  [ BLOCK: {block.block_name} ]  (Students in Block: {block.size})\n")
                        f.write(f"  {'-'*75}\n")

                        for term in Term.objects.filter(block=block):
                            f.write(f"    TERM: {term.term_name}\n")
                            
                            row_format = "{:<12} {:<8} {:<6} {:<10} {:<15} {:<15}"
                            header = row_format.format("Code", "Sec", "Type", "Days", "Time", "Enrl/Cap")
                            f.write("      " + header + "\n")
                            
                            scheduled_codes = set()
                            # FIXED: Use the helper to properly load courses without MultipleObjectsReturned exceptions
                            existing_groups = self._get_existing_course_objects_for_term(term)
                            
                            if existing_groups:
                                for group in existing_groups:
                                    for course in group:
                                        scheduled_codes.add(course.course_code)
                                        s_time = self._format_time(course.start_time)
                                        e_time = self._format_time(course.end_time)
                                        time_str = f"{s_time}-{e_time}"
                                        cap_str = str(course.capacity) if course.capacity else "?"
                                        ratio_str = f"{course.enrolled}/{cap_str}"
                                        f.write("      " + row_format.format(
                                            course.course_code, course.section,
                                            course.instr_type, course.days or "N/A",
                                            time_str, ratio_str
                                        ) + "\n")
                            else:
                                f.write("      (No courses assigned)\n")

                            elective_filter = {"course_code__icontains": "Elective"} if self.SKIP_ELECTIVES else {}
                            required_courses = ProgramCourse.objects.filter(
                                program=program, 
                                term=term.term_name
                            ).exclude(course_code__icontains="Elective").values_list('course_code', flat=True)
                            
                            missing_set = set(required_courses) - scheduled_codes
                            if missing_set:
                                f.write("      " + "-"*65 + "\n")
                                f.write(f"      !! MISSING / UNSCHEDULED: {', '.join(missing_set)}\n")
                                f.write("      " + "-"*65 + "\n")
                            f.write("\n")
                    f.write("\n\n")
            self._emit("Export complete.", "success")
        except IOError as e:
            self._emit(f"Error writing to file: {e}", "error")

    def export_visual_grid(self, filename="visual_schedule.txt"):
        self._emit(f"Generating box-style schedule to {filename}...")
        START_HOUR, END_HOUR, SLOT_MINS, COL_WIDTH = 8, 22, 30, 14
        total_slots = ((END_HOUR - START_HOUR) * 60) // SLOT_MINS
        days_map = {'M': 0, 'T': 1, 'W': 2, 'R': 3, 'F': 4}
        day_headers = ["MON", "TUE", "WED", "THU", "FRI"]

        try:
            with open(filename, "w", encoding="utf-8") as f:
                for program in Program.objects.all().order_by('program_name'):
                    for block in Block.objects.filter(program=program).order_by('block_name'):
                        for term in Term.objects.filter(block=block):
                            grid = [[None for _ in range(5)] for _ in range(total_slots)]
                            
                            # FIXED: Call the same existing objects helper to retrieve components
                            existing_groups = self._get_existing_course_objects_for_term(term)
                            
                            for group in existing_groups:
                                for course in group:
                                    if not course.days or not course.start_time: continue
                                    s_min = self.parse_time(course.start_time)
                                    e_min = self.parse_time(course.end_time)
                                    start_slot = (s_min - (START_HOUR * 60)) // SLOT_MINS
                                    end_slot = (e_min - (START_HOUR * 60)) // SLOT_MINS
                                    days = parse_days(course.days)
                                    
                                    for d in days:
                                        if d in days_map:
                                            for r in range(start_slot, end_slot):
                                                if 0 <= r < total_slots:
                                                    grid[r][d_idx] = course

                            title = f"{program.program_name} - {block.block_name} ({term.term_name})"
                            f.write("\n" + "="*85 + "\n")
                            f.write(f"{title:^85}\n")
                            f.write("="*85 + "\n\n")
                            header_row = " " * 7
                            for d in day_headers: header_row += f"{d:^{COL_WIDTH}} "
                            f.write(header_row + "\n")
                            
                            for r in range(total_slots):
                                border_str = " " * 7
                                has_border = False
                                for d in range(5):
                                    curr = grid[r][d]
                                    prev = grid[r-1][d] if r > 0 else None
                                    if (curr and curr != prev) or (prev and not curr) or (prev and curr and prev != curr):
                                        border_str += "+" + "-"*(COL_WIDTH-2) + "+ "
                                        has_border = True
                                    else:
                                        border_str += " " * (COL_WIDTH + 1)
                                if has_border: f.write(border_str + "\n")

                                time_label = "       "
                                for d in range(5):
                                    curr = grid[r][d]
                                    prev = grid[r-1][d] if r > 0 else None
                                    if curr and curr != prev:
                                        time_label = f"{self._format_time(curr.start_time):<7}"
                                        break

                                content_str = f"{time_label}"
                                for d in range(5):
                                    curr = grid[r][d]
                                    prev = grid[r-1][d] if r > 0 else None
                                    if curr:
                                        text = ""
                                        if curr != prev: text = curr.course_code
                                        elif r > 1 and grid[r-2][d] != curr: text = curr.instr_type
                                        content_str += f"| {text:^{COL_WIDTH-4}} | "
                                    else:
                                        content_str += " " * (COL_WIDTH + 1)
                                f.write(content_str + "\n")
                            f.write("\n")
            self._emit("Visual box export complete.", "success")
        except IOError as e:
            print(f"Error: {e}")

    def _format_time(self, time_str):
        if not time_str or len(str(time_str)) < 3:
            return ""
        t = str(time_str)
        if len(t) == 3: t = "0" + t
        return f"{t[:2]}:{t[2:]}"
            
    def parse_time(self, t):
        try:
            if not t: return 0
            t_int = int(t)
            return (t_int // 100 * 60) + (t_int % 100)
        except: return 0
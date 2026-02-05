import math
from django.utils import timezone
from data_app import models
from data_app.models import Course, Program, Block, ProgramCourse, Term, Student, TermCourses
import random
from django.db import models
from .schedule_validator import can_add_group_to_term
from django.db import transaction
from .utils import *

class ScheduleBuilder:

    BLOCK_SIZE = 20
    SHARED_COURSES = {}

    def build_blocks(self):
        """
        Creates Block and Term objects based on Program enrollment.
        """
        for program in Program.objects.all():
            self._build_blocks_for_program(program)

    def _build_blocks_for_program(self, program: Program):
        enrolled = program.enrolled or 0

        if enrolled <= 0:
            print(f"Error : Program {program.program_name} has no enrolled students.")
            return
    
        num_blocks = math.ceil(enrolled / self.BLOCK_SIZE)
        
        print(f"Building blocks for program: {program.program_name} with {enrolled} enrolled students.")

        # Delete old blocks
        Block.objects.filter(program=program).delete()

        for i in range(num_blocks):
            block_name = f"Block {chr(ord('A') + i)}"
            
            # Calculate capacity: last block gets remaining students, others get full BLOCK_SIZE
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
            
        print(f"Created {num_blocks} blocks for program: {program.program_name}")

    def find_shared_courses(self):
        """
        Prioritizes courses by:
        1. Program Frequency (Constraints)
        2. Flexibility (Fewest sections first)
        3. Random weight (To vary results on retries)
        """
        course_stats = (
            ProgramCourse.objects
            .exclude(course_code__icontains="Elective")  # <--- FIX: Ignore ElectiveA, ElectiveB, etc.
            .values('course_code')
            .annotate(program_count=models.Count('program', distinct=True))
        )
        enriched_stats = []
        for entry in course_stats:
            code = entry['course_code']
            
            # Get total number of distinct sections (bundles)
            # A course with fewer bundles is HARDER to schedule.
            num_bundles = len(self.get_course_bundles(code))

            enriched_stats.append({
                'course_code': code,
                'program_count': entry['program_count'],
                'flexibility': num_bundles, 
                'random_weight': random.random()
            })
        
        # Sort Logic:
        # 1. Most Programs (Constraints)
        # 2. FEWEST bundles (Flexibility - Low is hard) -> Use negative or reverse sort
        enriched_stats.sort(
            key=lambda x: (x['program_count'], -x['flexibility'], x['random_weight']),
            reverse=True
        )

        return enriched_stats
    
    def get_course_bundles(self, course_code):
        """
        Return a list of all possible course bundles for a given course code.
        """
        parents = Course.objects.filter(
            course_code=course_code,
            parent__isnull=True
        )
        
        bundles = []

        # For each parent, find all combinations of its children (labs, tuts)
        for parent in parents:
            children = parent.children.all()

            labs = [c for c in children if c.instr_type == "LAB"]
            tuts = [c for c in children if c.instr_type == "TUT"]

            if not labs and not tuts:
                bundles.append([parent])
                continue

            for lab in (labs or [None]):
                for tut in (tuts or [None]):
                    bundle = [parent]
                    if lab: bundle.append(lab)
                    if tut: bundle.append(tut)
                    bundles.append(bundle)

        return bundles
    
    def generate_schedule(self):
        MAX_RETRIES = 1  # Try up to 50 times to get a perfect schedule
        
        print(f"\n=== STARTING SCHEDULE GENERATION (Max Retries: {MAX_RETRIES}) ===")
        
        # 1. Build the Structure ONCE
        self.build_blocks()
        
        if Block.objects.count() == 0:
            print("CRITICAL ERROR: No blocks were created. Check 'Program' table and 'enrolled' count.")
            return

        for attempt in range(1, MAX_RETRIES + 1):
            print(f"\n>>> ATTEMPT {attempt} / {MAX_RETRIES}")

            # 2. Clear ONLY the schedule assignments
            with transaction.atomic():
                TermCourses.objects.all().delete()
                Course.objects.update(enrolled=0)
            
            # 3. Get Courses (Includes Random Weight for variation)
            sorted_courses = self.find_shared_courses()
            
            if len(sorted_courses) == 0:
                print("CRITICAL ERROR: No shared courses found. Check 'ProgramCourse' table.")
                return

            # 4. Run the Scheduling Logic
            for course_info in sorted_courses:
                course_code = course_info['course_code']
                # print(f"--- Processing: {course_code} ---") 
                self._schedule_course_globally(course_code)

            # 5. Check Result
            missing_count = self._count_missing_courses()
            
            if missing_count == 0:
                print(f"\nSUCCESS: Perfect schedule generated on attempt {attempt}!")
                break
            else:
                print(f"      [!] Attempt {attempt} result: {missing_count} courses missing.")
                if attempt == MAX_RETRIES:
                    print("\nWARNING: Max retries reached. The schedule is incomplete.")

        print("\n=== GENERATION COMPLETE ===")

    def _count_missing_courses(self):
        """
        Helper to count exactly how many required courses (excluding electives) failed to be scheduled.
        """
        missing_count = 0
        programs = Program.objects.all()
        for program in programs:
            blocks = Block.objects.filter(program=program)
            for block in blocks:
                terms = Term.objects.filter(block=block)
                for term in terms:
                    # 1. What does the program REQUIRE? (Exclude Electives)
                    required_codes = set(
                        ProgramCourse.objects.filter(
                            program=program, 
                            term=term.term_name
                        )
                        .exclude(course_code__icontains="Elective") # <--- FIX: Case-insensitive ignore
                        .values_list('course_code', flat=True)
                    )
                    
                    # 2. What is actually SCHEDULED?
                    scheduled_codes = set(
                        TermCourses.objects.filter(term=term)
                        .values_list('course_code', flat=True)
                    )
                    
                    missing = required_codes - scheduled_codes
                    missing_count += len(missing)
        
        return missing_count

    def _schedule_course_globally(self, course_code, depth=0):
        """
        Attempts to schedule the given course_code into all terms that require it.
        Added recursion depth to prevent infinite swapping loops.
        """
        MAX_RECURSION_DEPTH = 3  
        
        if depth > MAX_RECURSION_DEPTH:
            print(f"      [!] Max depth reached. Cannot schedule {course_code}.")
            return False

        bundles = self.get_course_bundles(course_code)
        if not bundles:
            return False

        # Find all terms that need this course
        targets = self._get_terms_needing_course(course_code)
        
        # Filter targets: only keep terms where this course isn't ALREADY scheduled
        targets = [t for t in targets if not TermCourses.objects.filter(term=t, course_code=course_code).exists()]

        random.shuffle(targets)

        for term in targets:
            # 1. Try Standard Greedy Schedule
            success = self._attempt_to_schedule_term(term, course_code, bundles)
            
            # 2. If Greedy failed, try "Kick and Repair"
            if not success and depth < MAX_RECURSION_DEPTH:
                # print(f"      [?] Conflict in {term.term_name}. Attempting to resolve...")
                success = self._attempt_force_schedule(term, course_code, bundles, depth)

            if not success:
                 print(f"      [x] Failed to place {course_code} in {term.term_name}")

    def _attempt_force_schedule(self, term, new_course_code, new_bundles, depth):
        """
        Kick and Repair logic with smart victim selection.
        """
        existing_groups = self._get_existing_course_objects_for_term(term)
        
        # Sort victims by "Ease of Rescheduling" (Flexibility)
        victim_scores = []
        for group in existing_groups:
            c_code = group[0].course_code
            num_options = len(self.get_course_bundles(c_code))
            victim_scores.append({
                'group': group,
                'code': c_code,
                'score': num_options
            })
        
        # Sort: Highest score (easiest to move) first
        victim_scores.sort(key=lambda x: x['score'], reverse=True)

        random.shuffle(new_bundles)

        for new_bundle in new_bundles:
            # Iterate through our SORTED list of victims
            for item in victim_scores:
                existing_group = item['group']
                victim_code = item['code']
                
                if victim_code == new_course_code: 
                    continue

                # Create temp schedule without this victim
                temp_schedule = [
                    g['group'] for g in victim_scores 
                    if g['code'] != victim_code
                ]
                
                if can_add_group_to_term(new_bundle, temp_schedule):
                    
                    # 1. Delete Victim and decrement enrollment for SPECIFIC sections
                    print(f"      [!] Kicking out {victim_code} to make room for {new_course_code}...")
                    
                    block_size = term.block.size
                    
                    # Decrement enrollment for each specific course in the victim bundle
                    for course_part in existing_group:
                        Course.objects.filter(pk=course_part.pk).update(
                            enrolled=models.F('enrolled') - block_size
                        )
                    
                    # Delete the TermCourses entries
                    TermCourses.objects.filter(term=term, course_code=victim_code).delete()

                    # 2. Add New Course
                    self._commit_bundle_to_term(term, new_bundle, block_size)
                    
                    # 3. Recurse (Try to fix the victim)
                    self._schedule_course_globally(victim_code, depth=depth + 1)
                    
                    return True 

        return False

    def _get_terms_needing_course(self, course_code):
        targets = []
        requirements = ProgramCourse.objects.filter(course_code=course_code)

        for req in requirements:
            blocks = Block.objects.filter(program=req.program)
            for block in blocks:
                terms = Term.objects.filter(block=block, term_name=req.term)
                targets.extend(terms)
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
        existing_groups = []
        
        grouped_codes = {}
        for entry in scheduled_entries:
            if entry.course_code not in grouped_codes:
                grouped_codes[entry.course_code] = []
            grouped_codes[entry.course_code].append(entry.section)

        for code, sections in grouped_codes.items():
            courses = list(Course.objects.filter(course_code=code, section__in=sections))
            if courses:
                existing_groups.append(courses)

        return existing_groups

    def _has_capacity(self, bundle, block_size):
        for course_part in bundle:
            if course_part.capacity is not None:
                if (course_part.enrolled + block_size) > course_part.capacity:
                    return False
        return True

    def _commit_bundle_to_term(self, term, bundle, block_size):
        with transaction.atomic():
            for course_part in bundle:
                TermCourses.objects.create(
                    term=term,
                    course_code=course_part.course_code,
                    section=course_part.section
                )
                Course.objects.filter(pk=course_part.pk).update(
                    enrolled=models.F('enrolled') + block_size
                )
                course_part.enrolled += block_size

    def export_schedule_to_txt(self, filename="generated_schedule.txt"):
        print(f"Exporting schedule to {filename}...")
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

                        terms = Term.objects.filter(block=block)
                        for term in terms:
                            f.write(f"    TERM: {term.term_name}\n")
                            
                            term_links = TermCourses.objects.filter(term=term)
                            row_format = "{:<12} {:<8} {:<6} {:<10} {:<15} {:<15}"
                            header = row_format.format("Code", "Sec", "Type", "Days", "Time", "Enrl/Cap")
                            f.write("      " + header + "\n")
                            
                            scheduled_codes = set()
                            if term_links.exists():
                                for link in term_links:
                                    scheduled_codes.add(link.course_code)
                                    try:
                                        course = Course.objects.get(
                                            course_code=link.course_code, 
                                            section=link.section
                                        )
                                        s_time = self._format_time(course.start_time)
                                        e_time = self._format_time(course.end_time)
                                        time_str = f"{s_time}-{e_time}"
                                        cap_str = str(course.capacity) if course.capacity else "?"
                                        ratio_str = f"{course.enrolled}/{cap_str}"
                                        
                                        f.write("      " + row_format.format(
                                            course.course_code,
                                            course.section,
                                            course.instr_type,
                                            course.days or "N/A",
                                            time_str,
                                            ratio_str
                                        ) + "\n")
                                    except:
                                        f.write(f"      ERR: {link.course_code}\n")
                            else:
                                f.write("      (No courses assigned)\n")

                            # --- DETECT MISSING (Ignoring Electives) ---
                            required_courses = ProgramCourse.objects.filter(
                                program=program, 
                                term=term.term_name
                            ).exclude(course_code__icontains="Elective").values_list('course_code', flat=True) # <--- FIX
                            
                            required_set = set(required_courses)
                            missing_set = required_set - scheduled_codes

                            if missing_set:
                                f.write("      " + "-"*65 + "\n")
                                f.write(f"      !! MISSING / UNSCHEDULED: {', '.join(missing_set)}\n")
                                f.write("      " + "-"*65 + "\n")
                            f.write("\n")
                    f.write("\n\n")
            print("Export complete.")
        except IOError as e:
            print(f"Error writing to file: {e}")

    def _format_time(self, time_str):
        if not time_str or len(str(time_str)) < 3:
            return ""
        t = str(time_str)
        if len(t) == 3: t = "0" + t
        return f"{t[:2]}:{t[2:]}"
    
    def export_visual_grid(self, filename="visual_schedule.txt"):
        print(f"Generating box-style schedule to {filename}...")
        START_HOUR, END_HOUR, SLOT_MINS, COL_WIDTH = 8, 22, 30, 14
        total_slots = ((END_HOUR - START_HOUR) * 60) // SLOT_MINS
        days_map = {'M': 0, 'T': 1, 'W': 2, 'R': 3, 'F': 4}
        day_headers = ["MON", "TUE", "WED", "THU", "FRI"]

        try:
            with open(filename, "w", encoding="utf-8") as f:
                programs = Program.objects.all().order_by('program_name')
                for program in programs:
                    blocks = Block.objects.filter(program=program).order_by('block_name')
                    for block in blocks:
                        terms = Term.objects.filter(block=block)
                        for term in terms:
                            grid = [[None for _ in range(5)] for _ in range(total_slots)]
                            term_links = TermCourses.objects.filter(term=term)
                            
                            for link in term_links:
                                try:
                                    course = Course.objects.get(course_code=link.course_code, section=link.section)
                                    if not course.days or not course.start_time: continue
                                    s_min = self.parse_time(course.start_time)
                                    e_min = self.parse_time(course.end_time)
                                    start_slot = (s_min - (START_HOUR * 60)) // SLOT_MINS
                                    end_slot = (e_min - (START_HOUR * 60)) // SLOT_MINS
                                    days = parse_days(course.days)
                                    for d in days:
                                        if d in days_map:
                                            d_idx = days_map[d]
                                            for r in range(start_slot, end_slot):
                                                if 0 <= r < total_slots:
                                                    grid[r][d_idx] = course
                                except: continue

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
                                    if curr and (curr != prev):
                                        border_str += "+" + "-"*(COL_WIDTH-2) + "+ "
                                        has_border = True
                                    elif prev and (not curr):
                                        border_str += "+" + "-"*(COL_WIDTH-2) + "+ "
                                        has_border = True
                                    elif prev and curr and (prev != curr):
                                        border_str += "+" + "-"*(COL_WIDTH-2) + "+ "
                                        has_border = True
                                    else:
                                        border_str += " " * (COL_WIDTH + 1)
                                if has_border: f.write(border_str + "\n")

                                time_label = "       "
                                for d in range(5):
                                    curr = grid[r][d]
                                    prev = grid[r-1][d] if r > 0 else None
                                    if curr and (curr != prev):
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
            print("Visual box export complete.")
        except IOError as e:
            print(f"Error: {e}")
            
    def parse_time(self, t):
        try:
            if not t: return 0
            t_int = int(t)
            return (t_int // 100 * 60) + (t_int % 100)
        except: return 0
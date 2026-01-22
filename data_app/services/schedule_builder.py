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
        Docstring for build_blocks
        
        :param self: Description
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

        #Delete old blocks
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

            Term.objects.create(block = block, term_name = "fall")
            Term.objects.create(block = block, term_name = "winter")
            
        print(f"Created {num_blocks} blocks for program: {program.program_name}")

    def find_shared_courses(self):
        """
        Creates a list of shared courses across all programs ordered by frequency.
        """
        course_stats = (
            ProgramCourse.objects
            .values('course_code')
            .annotate(program_count=models.Count('program', distinct = True))
        )
        # Enrich with complexity and random weight
        enriched_stats = []
        for entry in course_stats:
            code = entry['course_code']

            component_count = Course.objects.filter(course_code=code).count()

            # Higher component count = more complex to schedule
            enriched_stats.append({
                'course_code':code,
                'program_count':entry['program_count'],
                'complexity': component_count,
                'random_weight': random.random()
            })
        
        # Sort by program_count DESC, complexity DESC, random_weight ASC
        enriched_stats.sort(
            key=lambda x: (x['program_count'], -x['complexity'], x['random_weight']),
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

            labs = [c for c in children if c.instr_type =="LAB"]
            tuts = [c for c in children if c.instr_type =="TUT"]

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
        print("\n=== STARTING SCHEDULE GENERATION ===")
        
        #Clear old data
        TermCourses.objects.all().delete()
        Course.objects.update(enrolled=0)
        print("Old data cleared.")

        #Initalize Block objects in DB
        self.build_blocks()
        total_blocks = Block.objects.count()
        total_terms = Term.objects.count()
        print(f"STATUS: Created {total_blocks} blocks and {total_terms} terms.")
        
        if total_blocks == 0:
            print("CRITICAL ERROR: No blocks were created. Check 'Program' table and 'enrolled' count.")
            return

        #Get Courses for scheduling and order them by difficulty of scheduling
        sorted_courses = self.find_shared_courses()
        print(f"STATUS: Found {len(sorted_courses)} unique courses defined in ProgramCourse table.")
        
        if len(sorted_courses) == 0:
            # No shared courses found error
            print("CRITICAL ERROR: No shared courses found. Check 'ProgramCourse' table.")
            return

        #Loop through each course and try to schedule it globally
        for course_info in sorted_courses:
            course_code = course_info['course_code']
            print(f"\n--- Processing: {course_code} ---")
            self._schedule_course_globally(course_code)

        print("\n=== GENERATION COMPLETE ===")

    def _schedule_course_globally(self, course_code):
        """
        Attempts to schedule the given course_code into all terms that require it.
        """
        bundles = self.get_course_bundles(course_code)
        if not bundles:
            # No valid bundles found error
            print(f"   [!] SKIPPING: No valid bundles (sections) found for {course_code} in Course table.")
            return

        # Find all terms that need this course
        targets = self._get_terms_needing_course(course_code)
        if not targets:
            # No terms need this course Error
            print(f"   [!] SKIPPING: No Terms found that require {course_code}.")
            print(f"       (Hint: Check if ProgramCourse.term matches Term.term_name exactly)")
            return

        print(f"   > Found {len(bundles)} possible bundles.")
        print(f"   > Found {len(targets)} terms needing this course.")

        random.shuffle(targets)

        success_count = 0
        # Try to schedule into each target term
        for term in targets:
            success = self._attempt_to_schedule_term(term, course_code, bundles)
            if success:
                success_count += 1
            else:
                print(f"      [x] Failed to fit into {term.block.program.program_name} - {term.term_name} (Conflict/Capacity)")
        
        print(f"   > Successfully assigned to {success_count} / {len(targets)} terms.")

    def _get_terms_needing_course(self, course_code):
        """
        Returns a list of Term objects that require the given course_code.
        """
        targets = []
        
        #Finds all ProgramCourse entries for this course_code
        requirements = ProgramCourse.objects.filter(course_code=course_code)

        for req in requirements:
            # Find all blocks for the program
            blocks = Block.objects.filter(program=req.program)
            
            for block in blocks:
                # Find the term(s) in the block that match the requirement
                terms = Term.objects.filter(block=block, term_name=req.term)
                targets.extend(terms)
        
        return targets

    def _attempt_to_schedule_term(self, term, course_code, bundles):
        """
        Tries to schedule a course into a term. 
        """
        block_size = term.block.size or 0
        current_term_courses_objects = self._get_existing_course_objects_for_term(term)

        # Shuffle to ensure randomness
        random.shuffle(bundles)

        fail_cap = 0
        fail_time = 0
        total_bundles = len(bundles)

        for bundle in bundles:
            # Check Capacity of courses in bundle
            if not self._has_capacity(bundle, block_size):
                fail_cap += 1
                continue

            # Check Time Conflicts
            if not can_add_group_to_term(bundle, current_term_courses_objects):
                fail_time += 1
                continue

            # Insert Bundle into block term
            self._commit_bundle_to_term(term, bundle, block_size)
            return True

        # Debug Statments
        print(f"      [x] FAILED: {course_code} -> {term.block.program.program_name} ({term.term_name})")
        print(f"          - Total options tried: {total_bundles}")
        print(f"          - Rejected for Capacity: {fail_cap}")
        print(f"          - Rejected for Time Conflict: {fail_time}")
        
        return False

    def _get_existing_course_objects_for_term(self, term):
        """
        Returns a list of lists of Course objects already scheduled in the term.
        """
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
        """
        Returns True if ALL parts of the bundle have room for the block.
        """
        for course_part in bundle:
            # Calculate remaining space
            if course_part.capacity is not None:
                if (course_part.enrolled + block_size) > course_part.capacity:
                    return False
        return True

    def _commit_bundle_to_term(self, term, bundle, block_size):
        """
        Updates the database to add the bundle to the term.
        Also updates enrollment counts.
        """
        with transaction.atomic():
            for course_part in bundle:
                # Create Termcourse link in DB
                TermCourses.objects.create(
                    term=term,
                    course_code=course_part.course_code,
                    section=course_part.section
                )
                # Update enrollment count
                Course.objects.filter(pk=course_part.pk).update(
                    enrolled=models.F('enrolled') + block_size
                )
                
                # Update in-memory object as well
                course_part.enrolled += block_size

    def export_schedule_to_txt(self, filename="generated_schedule.txt"):
        """
        Generates a hierarchical text file of the entire schedule.
        Structure: Program -> Block -> Term -> Courses
        Includes: Enrollment ratios and Missing Course warnings.
        """
        print(f"Exporting schedule to {filename}...")
        
        try:
            with open(filename, "w", encoding="utf-8") as f:
                
                # 1. Iterate over all Programs
                programs = Program.objects.all().order_by('program_name')
                
                for program in programs:
                    f.write("="*85 + "\n")
                    f.write(f"PROGRAM: {program.program_name} (Enrolled: {program.enrolled})\n")
                    f.write("="*85 + "\n")

                    # 2. Iterate over Blocks in the Program
                    blocks = Block.objects.filter(program=program).order_by('block_name')
                    
                    if not blocks.exists():
                        f.write("  No blocks generated.\n")
                        continue

                    for block in blocks:
                        f.write(f"\n  [ BLOCK: {block.block_name} ]  (Students in Block: {block.size})\n")
                        f.write(f"  {'-'*75}\n")

                        # 3. Iterate over Terms in the Block
                        terms = Term.objects.filter(block=block)
                        
                        for term in terms:
                            f.write(f"    TERM: {term.term_name}\n")
                            
                            # --- A. List Scheduled Courses ---
                            term_links = TermCourses.objects.filter(term=term)
                            
                            # Formatting: Added 'Enrl/Cap' column
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
                                        
                                        # Calc Ratio: "45/50"
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
                                        
                                    except Course.DoesNotExist:
                                        f.write(f"      ERR: {link.course_code} {link.section} (Details not found)\n")
                                    except Course.MultipleObjectsReturned:
                                        f.write(f"      ERR: {link.course_code} {link.section} (Duplicate Data)\n")
                            else:
                                f.write("      (No courses assigned)\n")

                            # --- B. Detect & List Missing Courses ---
                            # Check what was required by the Program for this specific Term name
                            required_courses = ProgramCourse.objects.filter(
                                program=program, 
                                term=term.term_name
                            ).values_list('course_code', flat=True)
                            
                            required_set = set(required_courses)
                            missing_set = required_set - scheduled_codes

                            if missing_set:
                                f.write("      " + "-"*65 + "\n")
                                f.write(f"      !! MISSING / UNSCHEDULED: {', '.join(missing_set)}\n")
                                f.write("      " + "-"*65 + "\n")

                            f.write("\n") # Spacing between terms
                    
                    f.write("\n\n") # Spacing between programs
            
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
        """
        Generates a visual schedule with ASCII boxes.
        The time column dynamically reflects the actual course start times (e.g., 11:35).
        """
        print(f"Generating box-style schedule to {filename}...")
        
        # --- CONFIGURATION ---
        START_HOUR = 8   
        END_HOUR = 22    
        SLOT_MINS = 30   
        COL_WIDTH = 14   
        
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
                            
                            # 1. SETUP THE DATA GRID
                            # We store the actual course object in the grid
                            grid = [[None for _ in range(5)] for _ in range(total_slots)]
                            
                            term_links = TermCourses.objects.filter(term=term)
                            
                            for link in term_links:
                                try:
                                    course = Course.objects.get(course_code=link.course_code, section=link.section)
                                    if not course.days or not course.start_time: continue

                                    # We use the time to determine WHICH SLOT index,
                                    # but we will print the actual specific time string later.
                                    s_min = self.parse_time(course.start_time)
                                    e_min = self.parse_time(course.end_time)
                                    
                                    start_slot = (s_min - (START_HOUR * 60)) // SLOT_MINS
                                    end_slot = (e_min - (START_HOUR * 60)) // SLOT_MINS
                                    
                                    days = parse_days(course.days)
                                    for d in days:
                                        if d in days_map:
                                            d_idx = days_map[d]
                                            # Mark slots as occupied
                                            for r in range(start_slot, end_slot):
                                                if 0 <= r < total_slots:
                                                    grid[r][d_idx] = course
                                except:
                                    continue

                            # 2. RENDER HEADER
                            title = f"{program.program_name} - {block.block_name} ({term.term_name})"
                            f.write("\n" + "="*85 + "\n")
                            f.write(f"{title:^85}\n")
                            f.write("="*85 + "\n\n")

                            header_row = " " * 7 
                            for d in day_headers:
                                header_row += f"{d:^{COL_WIDTH}} "
                            f.write(header_row + "\n")
                            
                            # 3. RENDER ROWS
                            for r in range(total_slots):
                                
                                # --- A. THE BORDER LINE (The "Lid") ---
                                # We check if a course is starting here (Current is Not None, Previous was None/Different)
                                border_str = " " * 7
                                has_border = False
                                
                                for d in range(5):
                                    curr = grid[r][d]
                                    prev = grid[r-1][d] if r > 0 else None
                                    
                                    if curr and (curr != prev):
                                        # Top of a new box
                                        border_str += "+" + "-"*(COL_WIDTH-2) + "+ "
                                        has_border = True
                                    elif prev and (not curr):
                                        # Bottom of an old box (just ended)
                                        border_str += "+" + "-"*(COL_WIDTH-2) + "+ "
                                        has_border = True
                                    elif prev and curr and (prev != curr):
                                        # Back-to-back courses (One ended, one started)
                                        border_str += "+" + "-"*(COL_WIDTH-2) + "+ "
                                        has_border = True
                                    else:
                                        # Empty or middle of box
                                        border_str += " " * (COL_WIDTH + 1)
                                
                                if has_border:
                                    f.write(border_str + "\n")

                                # --- B. THE CONTENT LINE ---
                                # Determine the Time Label for the left column
                                time_label = "       " # Default blank
                                
                                # Scan row to see if any course starts exactly here to assume the label
                                for d in range(5):
                                    curr = grid[r][d]
                                    prev = grid[r-1][d] if r > 0 else None
                                    if curr and (curr != prev):
                                        # A course starts here, grab its time!
                                        formatted_time = self._format_time(curr.start_time)
                                        time_label = f"{formatted_time:<7}" 
                                        break # Found a time, stop looking

                                content_str = f"{time_label}"
                                
                                for d in range(5):
                                    curr = grid[r][d]
                                    prev = grid[r-1][d] if r > 0 else None
                                    
                                    if curr:
                                        # What to print inside?
                                        text = ""
                                        # If it's the first slot of the block
                                        if curr != prev:
                                            text = curr.course_code
                                        # If it's the second slot (optional detail)
                                        elif r > 1 and grid[r-2][d] != curr:
                                            text = curr.instr_type 
                                        
                                        content_str += f"| {text:^{COL_WIDTH-4}} | "
                                    else:
                                        content_str += " " * (COL_WIDTH + 1)
                                
                                f.write(content_str + "\n")

                            f.write("\n") # Spacing

            print("Visual box export complete.")

        except IOError as e:
            print(f"Error: {e}")
            
    def parse_time(self, t):
        """
        Converts 'HHMM' string/int to minutes from midnight.
        Example: '0830' -> 510 minutes.
        """
        try:
            if not t:
                return 0
            
            # Handle potential string inputs like "0830"
            t_int = int(t)
            
            hours = t_int // 100
            minutes = t_int % 100
            
            return (hours * 60) + minutes
        except (ValueError, TypeError):
            # Return 0 or a safe fallback if data is bad
                return 0
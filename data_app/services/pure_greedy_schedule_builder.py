import random
from .schedule_builder import ScheduleBuilder
from .schedule_validator import can_add_group_to_term

class PureGreedyScheduleBuilder(ScheduleBuilder):
    """
    A version of ScheduleBuilder that does not use ranking to select bundles.
    It simply picks the first valid bundle that fits for each term.
    """
    def _attempt_to_schedule_term(self, term, course_code, bundles):
        block_size = term.block.size or 0
        current_term_courses_objects = self._get_existing_course_objects_for_term(term)
        random.shuffle(bundles)
        for bundle in bundles:
            if not self._has_capacity(bundle, block_size):
                continue
            if not can_add_group_to_term(bundle, current_term_courses_objects):
                continue
            # Just pick the first valid bundle, do not score
            self._commit_bundle_to_term(term, bundle, block_size)
            return True
        return False

"""
Logging service for the Schedule Manager application.

Provides a simple interface for creating log entries that are persisted
to the database via the LogEntry model.
"""

from data_app.models import AdminUser, LogEntry


def create_log(action, details=None, level="INFO", admin=None):
    """
    Create a LogEntry record in the database.

    Args:
        action  (str):  Short description of what happened,
                        e.g. "Schedule Generated", "Blocks Ranked".
        details (str):  Optional longer text with extra context
                        (log output, error tracebacks, etc.).
        level   (str):  One of "INFO", "SUCCESS", "WARNING", "ERROR".
                        Defaults to "INFO".
        admin:          An AdminUser instance, an AdminUser pk (int),
                        or None for system-level actions.

    Returns:
        LogEntry: The newly created log entry instance.
    """
    # Resolve admin if an integer pk was passed
    if isinstance(admin, int):
        try:
            admin = AdminUser.objects.get(pk=admin)
        except AdminUser.DoesNotExist:
            admin = None

    # Validate level
    valid_levels = {choice[0] for choice in LogEntry.LEVEL_CHOICES}
    if level not in valid_levels:
        level = "INFO"

    # Truncate details if absurdly large (keep last 50 000 chars)
    if details and len(details) > 50_000:
        details = "... [truncated] ...\n" + details[-50_000:]

    return LogEntry.objects.create(
        admin=admin,
        action=action,
        details=details,
        level=level,
    )


def log_info(action, details=None, admin=None):
    """Convenience wrapper - creates an INFO-level log."""
    return create_log(action, details=details, level="INFO", admin=admin)


def log_success(action, details=None, admin=None):
    """Convenience wrapper - creates a SUCCESS-level log."""
    return create_log(action, details=details, level="SUCCESS", admin=admin)


def log_warning(action, details=None, admin=None):
    """Convenience wrapper - creates a WARNING-level log."""
    return create_log(action, details=details, level="WARNING", admin=admin)


def log_error(action, details=None, admin=None):
    """Convenience wrapper - creates an ERROR-level log."""
    return create_log(action, details=details, level="ERROR", admin=admin)


def get_recent_logs(limit=50):
    """
    Return the most recent log entries (ordered newest-first).

    Args:
        limit (int): Maximum number of entries to return. Defaults to 50.

    Returns:
        QuerySet[LogEntry]
    """
    return LogEntry.objects.select_related("admin").order_by("-timestamp")[:limit]


def get_logs_by_action(action, limit=50):
    """
    Return log entries filtered by action keyword (case-insensitive contains).

    Args:
        action (str): Substring to search for in the action field.
        limit  (int): Maximum number of entries to return.

    Returns:
        QuerySet[LogEntry]
    """
    return (
        LogEntry.objects.select_related("admin")
        .filter(action__icontains=action)
        .order_by("-timestamp")[:limit]
    )


def get_logs_by_level(level, limit=50):
    """
    Return log entries filtered by level.

    Args:
        level (str): One of "INFO", "SUCCESS", "WARNING", "ERROR".
        limit (int): Maximum number of entries to return.

    Returns:
        QuerySet[LogEntry]
    """
    return (
        LogEntry.objects.select_related("admin")
        .filter(level=level)
        .order_by("-timestamp")[:limit]
    )


def clear_old_logs(keep=1000):
    """
    Delete all but the most recent *keep* log entries.

    Useful for periodic housekeeping so the log table doesn't grow
    unboundedly.

    Args:
        keep (int): Number of most-recent entries to preserve.

    Returns:
        int: Number of rows deleted.
    """
    ids_to_keep = LogEntry.objects.order_by("-timestamp").values_list("id", flat=True)[
        :keep
    ]
    deleted_count, _ = LogEntry.objects.exclude(id__in=list(ids_to_keep)).delete()
    return deleted_count

def format_hms(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total = int(max(0, round(float(seconds))))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

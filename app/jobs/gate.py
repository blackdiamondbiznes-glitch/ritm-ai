"""Reasons a daily job must stop instead of calling the model."""


def block_reason(*, active: bool, allowed: bool, has_profile: bool, quota: int) -> str | None:
    """Return a cancel code, or None when the job may generate."""
    if not active:
        return "inactive"
    if not has_profile:
        return "profile"
    if not allowed:
        return "module"
    if quota <= 0:
        return "quota"
    return None

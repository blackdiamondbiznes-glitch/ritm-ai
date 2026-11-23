"""Small JSON shapes for one student's lessons and reminders."""


def lesson_brief(row) -> dict:
    """The lesson fields the student profile shows."""
    return {
        "id": row.id,
        "title": row.title,
        "status": row.status,
        "starts_at": row.starts_at.isoformat() if row.starts_at else None,
        "amount_uzs": row.amount_uzs,
    }


def reminder_brief(row) -> dict:
    """The reminder fields the student profile shows."""
    return {
        "id": row.id,
        "text": row.text,
        "send_at": row.send_at.isoformat(),
        "sent": row.sent_at is not None,
    }

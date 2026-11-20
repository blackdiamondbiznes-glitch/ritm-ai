"""Where a quiz is answered. Telegram makes channel polls anonymous."""

QUIZ = "quiz"
ADMIN_POST_QUIZ = "admin_post_quiz"
DEEPLINK = "private_deeplink"
NATIVE = "group_native"


def delivery_mode(chat_type: object) -> str:
    """Channels open a private quiz. Groups and supergroups use a native poll."""
    value = getattr(chat_type, "value", chat_type)
    if value == "channel":
        return DEEPLINK
    return NATIVE

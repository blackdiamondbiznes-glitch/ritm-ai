"""Router registration. Private menus are isolated from channel updates."""

from aiogram import Dispatcher, F, Router

from app.bot.routers import (
    admin,
    admin_health,
    admin_payments,
    admin_posts,
    chats,
    connect,
    daily,
    enroll,
    fallback,
    join,
    leaderboard,
    membership,
    payments,
    profile,
    quiz,
    quiz_link,
    quiz_play,
    quiz_poll,
    start,
    subscription,
)


def setup_routers(dispatcher: Dispatcher) -> None:
    """Include routers. Command router is first so /cancel wins over text steps."""
    private = Router(name="private")
    private.message.filter(F.chat.type == "private")
    private.callback_query.filter(F.message.chat.type == "private")
    private.include_router(quiz_link.router)
    private.include_router(join.router)
    private.include_router(start.router)
    private.include_router(connect.router)
    private.include_router(profile.router)
    private.include_router(chats.router)
    private.include_router(daily.router)
    private.include_router(quiz.router)
    private.include_router(leaderboard.router)
    private.include_router(quiz_play.router)
    private.include_router(subscription.router)
    private.include_router(payments.router)
    private.include_router(admin_payments.router)
    private.include_router(admin.router)
    private.include_router(admin_health.router)
    private.include_router(fallback.router)
    dispatcher.include_router(private)
    dispatcher.include_router(enroll.router)
    dispatcher.include_router(admin_posts.router)
    dispatcher.include_router(quiz_poll.router)
    dispatcher.include_router(membership.router)

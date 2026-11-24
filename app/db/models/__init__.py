"""ORM models. Importing this package registers every table on the metadata."""

from app.db.models.attendance import TutorAttendance
from app.db.models.audit import AuditLog
from app.db.models.cache import AiCache
from app.db.models.chats import Chat, ChatProfile, ChatType
from app.db.models.content import ContentItem, ContentKind
from app.db.models.groups import TutorGroup, TutorGroupMember
from app.db.models.homework_submissions import TutorHomeworkSubmission
from app.db.models.invoices import TutorFeePayment, TutorInvoice
from app.db.models.jobs import Job, JobStatus
from app.db.models.leaderboard import LeaderboardEntry, LeaderboardPeriod
from app.db.models.lessons import TutorLesson
from app.db.models.notifications import NotificationLog
from app.db.models.panel_tokens import PanelLoginToken
from app.db.models.payments import Payment, PaymentEvent
from app.db.models.plan_entitlements import PlanEntitlement
from app.db.models.plans import Plan
from app.db.models.quizzes import Quiz, QuizAnswer
from app.db.models.reminders import TutorReminder
from app.db.models.schedules import Schedule
from app.db.models.students import TutorStudent
from app.db.models.subscriptions import Subscription, SubscriptionSource, SubscriptionStatus
from app.db.models.system_state import SystemState
from app.db.models.topics import TutorScore, TutorTopic
from app.db.models.tutor_notices import TutorNotice
from app.db.models.usage import UsageCounter, UsageDaily
from app.db.models.users import User
from app.db.models.widget_messages import WidgetMessage
from app.db.models.workspace_members import WorkspaceMember
from app.db.models.workspaces import Workspace

__all__ = [
    "AiCache",
    "AuditLog",
    "Chat",
    "ChatProfile",
    "ChatType",
    "ContentItem",
    "ContentKind",
    "Job",
    "JobStatus",
    "NotificationLog",
    "PanelLoginToken",
    "Payment",
    "PaymentEvent",
    "PlanEntitlement",
    "LeaderboardEntry",
    "LeaderboardPeriod",
    "Plan",
    "Quiz",
    "QuizAnswer",
    "Schedule",
    "TutorReminder",
    "Subscription",
    "SubscriptionSource",
    "SubscriptionStatus",
    "SystemState",
    "TutorAttendance",
    "TutorFeePayment",
    "TutorGroup",
    "TutorHomeworkSubmission",
    "TutorInvoice",
    "TutorGroupMember",
    "TutorLesson",
    "TutorNotice",
    "TutorScore",
    "TutorStudent",
    "TutorTopic",
    "UsageCounter",
    "UsageDaily",
    "User",
    "WidgetMessage",
    "Workspace",
    "WorkspaceMember",
]

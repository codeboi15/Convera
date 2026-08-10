"""ORM models. Importing them here registers their tables on ``Base.metadata``
so Alembic and ``create_all`` can see the full schema.
"""

from app.models.base import TimestampMixin, UUIDMixin
from app.models.contact import Contact
from app.models.conversation import Conversation, Message
from app.models.enums import (
    ArticleStatus,
    Channel,
    ConversationStatus,
    Role,
    SenderType,
)
from app.models.kb import KBArticle, KBCategory
from app.models.user import User
from app.models.workspace import Invite, Workspace, WorkspaceMember

__all__ = [
    "TimestampMixin",
    "UUIDMixin",
    "User",
    "Workspace",
    "WorkspaceMember",
    "Invite",
    "Contact",
    "Conversation",
    "Message",
    "KBCategory",
    "KBArticle",
    "Role",
    "Channel",
    "ConversationStatus",
    "SenderType",
    "ArticleStatus",
]

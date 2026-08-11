from __future__ import annotations

import enum


class Role(str, enum.Enum):
    admin = "admin"
    agent = "agent"


class Channel(str, enum.Enum):
    chat = "chat"
    email = "email"


class ConversationStatus(str, enum.Enum):
    open = "open"
    snoozed = "snoozed"
    resolved = "resolved"


class SenderType(str, enum.Enum):
    contact = "contact"
    agent = "agent"
    system = "system"


class ArticleStatus(str, enum.Enum):
    draft = "draft"
    published = "published"

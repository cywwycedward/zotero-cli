"""Feed models for RSS query results (design §11.2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, computed_field


class FeedSummary(BaseModel):
    """A single feed subscription (feeds list)."""

    model_config = ConfigDict(extra="forbid")

    feed_id: int = Field(alias="libraryID")
    name: str
    url: str
    last_update: str | None = Field(default=None, alias="lastUpdate")
    last_check: str | None = Field(default=None, alias="lastCheck")
    last_check_error: str | None = Field(default=None, alias="lastCheckError")
    refresh_interval: int = Field(default=0, alias="refreshInterval")
    total_count: int = 0
    unread_count: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def key(self) -> str:
        """Used by --quiet output."""
        return str(self.feed_id)


class FeedItemCreator(BaseModel):
    """A single creator for a feed item."""

    model_config = ConfigDict(extra="forbid")

    first_name: str = ""
    last_name: str = ""
    creator_type: str = ""
    order_index: int = 0


class FeedItem(BaseModel):
    """A single feed item (feeds items query)."""

    model_config = ConfigDict(extra="forbid")

    feed_id: int
    item_id: int
    guid: str = ""
    title: str = ""
    date_raw: str = ""
    date_sql: str = ""
    url: str = ""
    abstract: str = ""
    read_time: str | None = None
    translated_time: str | None = None
    creators: list[FeedItemCreator] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def date(self) -> str:
        return self.date_raw

    @computed_field  # type: ignore[prop-decorator]
    @property
    def key(self) -> str:
        """Used by --quiet output."""
        return str(self.item_id)

"""Top-level shape of ``channels.yaml`` (channels + bindings)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.channel import ChannelBinding, ChannelConfig


class ChannelsFile(BaseModel):
    """Two parallel lists: declared channels and (channel, conduit) bindings."""

    channels: list[ChannelConfig] = Field(default_factory=list)
    bindings: list[ChannelBinding] = Field(default_factory=list)

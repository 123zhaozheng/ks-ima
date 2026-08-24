"""Transport-independent identity result contracts."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class IdentityUser(BaseModel):
    """Minimal identity projection shared by application and adapters."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    id: str
    email: str
    display_name: str
    image_url: str | None = None
    platform_roles: tuple[str, ...] = ()
    is_active: bool

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import APIModel

_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
LOGO_POSITIONS = ("top_left", "top_right", "bottom_left", "bottom_right")


def _hex(value: str | None) -> str | None:
    if value is None:
        return None
    if not _HEX.match(value):
        raise ValueError(f"'{value}' is not a valid hex colour (expected #RGB or #RRGGBB)")
    return value.upper()


class BrandKitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    brand_name: str = Field(default="", max_length=120)
    slogan: str = Field(default="", max_length=200)
    primary_color: str = "#FFFFFF"
    accent_color: str = "#FFD166"
    background_color: str = "#101014"
    font_family: str = Field(default="sans_bold", max_length=16)
    logo_position: str = "top_right"
    #: Logo width as a fraction of the frame. Above a third it stops being a
    #: watermark and starts covering the product.
    logo_scale: float = Field(default=0.16, ge=0.04, le=0.35)
    logo_opacity: float = Field(default=0.9, ge=0.1, le=1.0)

    @field_validator("primary_color", "accent_color", "background_color")
    @classmethod
    def _colour(cls, value: str) -> str:
        return _hex(value)  # type: ignore[return-value]

    @field_validator("logo_position")
    @classmethod
    def _position(cls, value: str) -> str:
        if value not in LOGO_POSITIONS:
            raise ValueError(f"logo_position must be one of {', '.join(LOGO_POSITIONS)}")
        return value


class BrandKitUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    brand_name: str | None = Field(default=None, max_length=120)
    slogan: str | None = Field(default=None, max_length=200)
    primary_color: str | None = None
    accent_color: str | None = None
    background_color: str | None = None
    font_family: str | None = Field(default=None, max_length=16)
    logo_position: str | None = None
    logo_scale: float | None = Field(default=None, ge=0.04, le=0.35)
    logo_opacity: float | None = Field(default=None, ge=0.1, le=1.0)

    @field_validator("primary_color", "accent_color", "background_color")
    @classmethod
    def _colour(cls, value: str | None) -> str | None:
        return _hex(value)

    @field_validator("logo_position")
    @classmethod
    def _position(cls, value: str | None) -> str | None:
        if value is not None and value not in LOGO_POSITIONS:
            raise ValueError(f"logo_position must be one of {', '.join(LOGO_POSITIONS)}")
        return value


class BrandKitResponse(APIModel):
    id: str
    name: str
    brand_name: str
    slogan: str
    primary_color: str
    accent_color: str
    background_color: str
    font_family: str
    logo_media_id: str | None = None
    logo_url: str | None = None
    logo_position: str
    logo_scale: float
    logo_opacity: float
    created_at: datetime
    updated_at: datetime

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.enums import CharacterKind
from app.schemas.common import APIModel


class CharacterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: CharacterKind = CharacterKind.ADULT
    age: str = Field(default="", max_length=60)
    gender: str = Field(default="", max_length=40)
    skin_tone: str = Field(default="", max_length=60)
    hair: str = Field(default="", max_length=120)
    clothes: str = Field(default="", max_length=300)
    headwear: str = Field(default="", max_length=160)
    expression: str = Field(default="", max_length=120)
    personality: str = Field(default="", max_length=200)
    environment: str = Field(default="", max_length=300)
    #: Leave empty to have it composed from the fields above.
    description: str = Field(default="", max_length=1200)


class CharacterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    kind: CharacterKind | None = None
    age: str | None = Field(default=None, max_length=60)
    gender: str | None = Field(default=None, max_length=40)
    skin_tone: str | None = Field(default=None, max_length=60)
    hair: str | None = Field(default=None, max_length=120)
    clothes: str | None = Field(default=None, max_length=300)
    headwear: str | None = Field(default=None, max_length=160)
    expression: str | None = Field(default=None, max_length=120)
    personality: str | None = Field(default=None, max_length=200)
    environment: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=1200)


class CharacterResponse(APIModel):
    id: str
    name: str
    kind: CharacterKind
    age: str
    gender: str
    skin_tone: str
    hair: str
    clothes: str
    headwear: str
    expression: str
    personality: str
    environment: str
    #: The frozen sentence replayed into every image prompt.
    description: str
    reference_media_id: str | None = None
    reference_image_url: str | None = None
    created_at: datetime
    updated_at: datetime

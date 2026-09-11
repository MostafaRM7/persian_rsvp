from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=72, description="Capped at 72 characters to match bcrypt truncation limit")
    email: Optional[str] = Field(default=None, max_length=255)


class UserLogin(BaseModel):
    username: str
    password: str = Field(..., max_length=72)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: Optional[str] = None
    preferred_wpm: int = 300
    created_at: datetime


class UserUpdate(BaseModel):
    preferred_wpm: Optional[int] = Field(default=None, ge=60, le=1200)
    email: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class TokenData(BaseModel):
    username: Optional[str] = None


class SavedTextCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=100_000)
    wpm: Optional[int] = Field(default=300, ge=60, le=1200)


class SavedTextUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    content: Optional[str] = Field(default=None, min_length=1, max_length=100_000)
    last_position: Optional[int] = Field(default=None, ge=0)
    wpm: Optional[int] = Field(default=None, ge=60, le=1200)


class SavedTextOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str
    last_position: int
    wpm: int
    created_at: datetime
    updated_at: datetime


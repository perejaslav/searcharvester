"""Shared response models for the Searcharvester API."""
from pydantic import BaseModel


class TavilyResult(BaseModel):
    url: str
    title: str
    content: str
    score: float
    raw_content: str | None = None


class TavilyResponse(BaseModel):
    query: str
    follow_up_questions: list[str] | None = None
    answer: str | None = None
    images: list[str] = []
    results: list[TavilyResult]
    response_time: float
    request_id: str

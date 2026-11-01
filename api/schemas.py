"""The JSON contract of the API, written as Pydantic models.

These models do three jobs at once:
  1. VALIDATE: if the pipeline ever returns something that breaks the contract, we find out
     immediately (a test fails, or the API answers 500) instead of sending bad JSON to a client.
  2. DOCUMENT: /docs (Swagger UI) is generated from them, so the documentation can never be out of date.
  3. ORDER: fields are returned in the order written here (headline near the top).

tests/test_api.py checks that these models match pipeline.schema.Article.to_dict().
"""
from typing import Literal

from pydantic import BaseModel, Field

PagePath = Literal["text_layer", "hybrid", "ocr"]


class ArticleMethod(BaseModel):
    path: PagePath = Field(description="how the page was read")
    summary: str = Field(description="how the summary was made", examples=["extractive"])


class ArticleOut(BaseModel):
    page: int
    type: str = Field(description="article class; everything is 'news' until the classifier exists")
    headline: str | None
    subhead: str | None
    text: str
    summary: str
    continues_on_page: int | None = Field(description="page where a 'continued on page N' story goes on")
    bbox: tuple[float, float, float, float] = Field(description="x0, y0, x1, y1 in PDF points")
    method: ArticleMethod
    warnings: list[str]


class PageOut(BaseModel):
    page: int = Field(description="1-based page number")
    path: PagePath
    seconds: float = Field(description="processing time for this page")
    articles: list[ArticleOut]


class ProcessResponse(BaseModel):
    file: str = Field(description="the name of the uploaded file")
    pages: list[PageOut]


class ErrorResponse(BaseModel):
    error: str


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    tesseract: str | None = Field(description="Tesseract version, or null if it cannot be found")

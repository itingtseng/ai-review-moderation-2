# backend/app.py
from fastapi import FastAPI
from pydantic import BaseModel
from .classifier import classify_review

app = FastAPI(title="AI Review Moderation 2.0 API")

class ReviewIn(BaseModel):
    text: str
    top_k: int = 5

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/classify")
def classify(in_: ReviewIn):
    return classify_review(in_.text, top_k=in_.top_k)

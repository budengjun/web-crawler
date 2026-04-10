from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class Job(BaseModel):
    title: str = Field(..., description="Job Title")
    company: str = Field(..., description="Company Name")
    location: str = Field(..., description="Job Location")
    description: str = Field(..., description="Full Job Description")
    apply_link: str = Field(..., description="URL to apply for the job")
    posted_date: Optional[datetime] = Field(None, description="Date the job was posted")
    
    # AI Filtering fields
    match_score: Optional[int] = Field(None, description="AI calculated match score (0-100)")
    match_reasoning: Optional[str] = Field(None, description="AI reasoning for the score")

    # Persistence / deduplication fields
    first_seen: Optional[datetime] = Field(None, description="Timestamp when this job was first scraped")
    notified: bool = Field(False, description="Whether a notification has been sent for this job")

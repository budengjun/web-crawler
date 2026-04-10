import asyncio
import google.generativeai as genai
import json
import logging
from models import Job
from typing import List
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# Max concurrent Gemini calls (Set to 1 for Free Tier to avoid concurrency issues)
_SEMAPHORE_LIMIT = 1
# AI Quota: Seconds to wait between requests to stay under 5 RPM limit
_QUOTA_WAIT_SECONDS = 12


class AIFilter:
    def __init__(self, api_key: str, keywords: List[str]):
        self.api_key = api_key
        self.keywords = keywords
        if self.api_key and self.api_key != "YOUR_GEMINI_API_KEY":
            genai.configure(api_key=self.api_key)
            # Use gemini-2.5-flash — fast and cost-effective for text
            self.model = genai.GenerativeModel(
                "gemini-2.5-flash",
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",  # Force structured JSON output
                ),
            )
        else:
            self.model = None
            logger.warning(
                "Gemini API key not configured or is default. AI Filtering will be skipped."
            )

    # ──────────────────────────────────────────────
    # Public: batch evaluation with bounded concurrency
    # ──────────────────────────────────────────────

    async def evaluate_jobs(self, jobs: List[Job]) -> List[Job]:
        """
        Evaluate a list of jobs concurrently using a semaphore to cap
        the number of simultaneous Gemini API calls.
        """
        if not self.model:
            for job in jobs:
                job.match_score = 0
                job.match_reasoning = "AI filtering disabled due to missing API key."
            return jobs

        sem = asyncio.Semaphore(_SEMAPHORE_LIMIT)

        async def _eval_with_sem(job: Job) -> Job:
            async with sem:
                res = await self.evaluate_job(job)
                # "Wait Room": Force a pause between requests to respect rate limits
                logger.info(f"Waiting {_QUOTA_WAIT_SECONDS}s to respect AI quota...")
                await asyncio.sleep(_QUOTA_WAIT_SECONDS)
                return res

        results = await asyncio.gather(
            *[_eval_with_sem(j) for j in jobs],
            return_exceptions=True,
        )

        evaluated: List[Job] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Job evaluation raised exception: {result}")
                jobs[i].match_score = 0
                jobs[i].match_reasoning = f"Evaluation failed: {result}"
                evaluated.append(jobs[i])
            else:
                evaluated.append(result)

        return evaluated

    # ──────────────────────────────────────────────
    # Single job evaluation (with retry)
    # ──────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=5, min=10, max=70),  # Longer wait for 429 recovery
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    async def evaluate_job(self, job: Job) -> Job:
        if not self.model:
            job.match_score = 0
            job.match_reasoning = "AI filtering disabled due to missing API key."
            return job

        prompt = f"""
        You are an expert technical recruiter and career advisor.
        Evaluate the following job description against a candidate whose profile is focused on "Full-stack" and "AI/ML".
        
        Candidate's preferred keywords/tech stack: {', '.join(self.keywords)}
        
        Job Title: {job.title}
        Company: {job.company}
        Job Description: {job.description[:4000]}
        
        Tasks:
        1. Determine if this job matches a "Full-stack" or "AI/ML" profile.
        2. Calculate a match score from 0 to 100 based on the presence of preferred keywords and overall role alignment.
        3. Provide a brief reasoning for the score.
        
        Return the result STRICTLY as a JSON object with the following schema:
        {{
            "score": <int>,
            "reasoning": "<string>"
        }}
        """

        try:
            response = await self.model.generate_content_async(prompt)

            text = response.text.strip()

            # Structured JSON output should already be clean, but handle fences as fallback
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            result = json.loads(text)
            job.match_score = result.get("score", 0)
            job.match_reasoning = result.get("reasoning", "No reasoning provided.")

            logger.info(f"Evaluated {job.title} at {job.company}: Score {job.match_score}")

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error for {job.title}: {e} — raw text: {text[:200]}")
            job.match_score = 0
            job.match_reasoning = f"Evaluation failed: could not parse AI response."
        except Exception as e:
            logger.error(f"Error evaluating job {job.title} with AI: {e}")
            raise  # Let tenacity retry

        return job

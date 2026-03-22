import google.generativeai as genai
import json
import logging
from models import Job
from typing import List

logger = logging.getLogger(__name__)

class AIFilter:
    def __init__(self, api_key: str, keywords: List[str]):
        self.api_key = api_key
        self.keywords = keywords
        if self.api_key and self.api_key != "YOUR_GEMINI_API_KEY":
            genai.configure(api_key=self.api_key)
            # 使用 gemini-2.5-flash 处理文本速度快且成本低
            self.model = genai.GenerativeModel('gemini-2.5-flash')
        else:
            self.model = None
            logger.warning("Gemini API key not configured or is default. AI Filtering will be skipped.")

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
        Job Description: {job.description[:4000]} # Truncate to avoid exceeding context limits and save tokens
        
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
            
            # 解析 JSON 结果
            text = response.text
            if text.startswith("```json"):
                text = text[7:-3]
            elif text.startswith("```"):
                text = text[3:-3]
                
            result = json.loads(text.strip())
            job.match_score = result.get("score", 0)
            job.match_reasoning = result.get("reasoning", "No reasoning provided.")
            
            logger.info(f"Evaluated {job.title} at {job.company}: Score {job.match_score}")
            
        except Exception as e:
            logger.error(f"Error evaluating job {job.title} with AI: {e}")
            job.match_score = 0
            job.match_reasoning = f"Evaluation failed: {str(e)}"

        return job

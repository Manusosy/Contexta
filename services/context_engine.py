import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from models import db, Article, Setting
from utils.logger import log_event as _log
import requests
from config import get_config

config = get_config()

# Basic prompt to force the model to score and classify the text.
CONTEXT_ANALYSIS_PROMPT = """
You are the "Context Analysis Engine" for an automated content curation platform.
Your task is to analyze the following extracted article text and return ONLY a JSON response with your analysis.

Analyze based on these criteria:
1. Topic Classification (e.g., Technology, Politics, Finance, Science, Sports, AI)
2. Content Value Scoring (0 to 100):
   - Is it highly relevant, well-written, and informative? (Higher score)
   - Is it just a short stub, heavily promotional, or very low context? (Lower score)
3. Content Strategy Decision:
   - "News Article", "Explainer", "Summary", "Opinion", "Skip" (if too short/poor quality)

Return ONLY valid JSON in this format:
{{
  "topic_category": "Topic Name",
  "relevance_score": 85,
  "trend_potential": "High/Medium/Low",
  "recommended_strategy": "Explainer",
  "reasoning": "Short 1-sentence explanation"
}}

Here is the extracted text to analyze (may be truncated):
---
{extracted_body}
---
"""

def analyze_article_context(article: Article) -> Dict[str, Any]:
    """
    Calls the AI model to perform topic classification and relevance scoring.
    Returns a dict containing the analysis. If the score is below threshold, 
    the article can be skipped by the automation service.
    """
    if not article.extracted_body or len(article.extracted_body.strip()) < 100:
        return {
            "topic_category": "Unknown",
            "relevance_score": 0,
            "recommended_strategy": "Skip",
            "reasoning": "Content too short or empty for analysis."
        }

    api_key = Setting.get("ai_api_key") or getattr(config, "OPENROUTER_API_KEY", None)
    if not api_key:
        _log("Context Engine skipped — no OpenRouter API key configured", "warning")
        return get_default_analysis()

    model = Setting.get("ai_model", "openai/gpt-4o-mini")
    # Quick analysis model - fallback to fast models if needed
    analysis_models = [model]
    if ":free" in model or "free" in model.lower():
        analysis_models.extend(["google/gemma-3-27b-it:free", "meta-llama/llama-3.3-70b-instruct:free"])
    
    prompt = CONTEXT_ANALYSIS_PROMPT.format(extracted_body=article.extracted_body[:8000])

    for current_model in analysis_models:
        try:
            payload = {
                "model": current_model,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }
            if "openai" in current_model.lower() or "gpt-4" in current_model.lower():
                payload["response_format"] = {"type": "json_object"}

            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://contexta.io",
                    "X-Title": "Contexta",
                },
                data=json.dumps(payload),
                timeout=30
            )

            if response.status_code == 200:
                result_json = response.json()
                raw_text = result_json['choices'][0]['message']['content']
                
                # Extract JSON
                clean = raw_text.strip()
                start_idx = clean.find("{")
                end_idx = clean.rfind("}")
                
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    clean = clean[start_idx : end_idx + 1]
                
                analysis = json.loads(clean)
                
                # Set database fields
                article.topic_category = analysis.get("topic_category", "General")
                try:
                    article.relevance_score = int(analysis.get("relevance_score", 0))
                except ValueError:
                    article.relevance_score = 50

                _log(f"Context analysis complete for '{article.original_title[:30]}': Score {article.relevance_score}, Strategy: {analysis.get('recommended_strategy')}", "success")
                return analysis
            elif response.status_code in [429, 502, 500, 400] and current_model != analysis_models[-1]:
                continue
            else:
                _log(f"Context Engine API error: {response.status_code}", "error", response.text)
                return get_default_analysis()

        except Exception as e:
            if current_model != analysis_models[-1]:
                continue
            _log("Context Engine analysis failed", "error", str(e))
            return get_default_analysis()

    return get_default_analysis()

def get_default_analysis() -> Dict[str, Any]:
    return {
        "topic_category": "General",
        "relevance_score": 60,
        "recommended_strategy": "News Article",
        "reasoning": "Fallback to default strategy due to analysis failure."
    }

def detect_duplicates(article: Article, threshold_hours: int = 24) -> bool:
    """
    Checks if a highly similar topic has been processed recently.
    Returns True if a duplicate is found (meaning this article should be skipped).
    """
    if not article.original_title:
        return False
        
    time_limit = datetime.now(timezone.utc) - timedelta(hours=threshold_hours)
    
    # We look for articles generated recently that are either "published" or "generated"
    recent_articles = Article.query.filter(
        Article.id != article.id,
        Article.created_at >= time_limit,
        Article.status.in_(["published", "generated", "pushed"])
    ).all()

    # Simple text similarity based on title comparison.
    # In a full intelligent system, this would use semantic similarity (e.g., embeddings)
    # For now, we do basic word overlap ratio.
    title_words = set(article.original_title.lower().split())
    if not title_words:
        return False

    for past_article in recent_articles:
        if not past_article.original_title:
            continue
            
        past_words = set(past_article.original_title.lower().split())
        if not past_words:
            continue
            
        intersection = title_words.intersection(past_words)
        # Jaccard index approx
        overlap_ratio = len(intersection) / float(len(title_words.union(past_words)))
        
        if overlap_ratio > 0.6:  # 60% word overlap threshold
            _log(f"Context Engine: Duplicate detected. '{article.original_title[:30]}' overlaps with '{past_article.original_title[:30]}'", "warning")
            return True

    return False

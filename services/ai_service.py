"""AI Service — generates editorial content via OpenRouter API."""
import json
import requests
from models import Setting, db, Article
from utils.logger import log_event as _log
from config import get_config

config = get_config()

SYSTEM_PROMPT = """
You are an expert content strategist and SEO copywriter.
Your job is to read a source article, deeply understand its topic,
key arguments, and facts — then produce a completely original,
plagiarism-free article on the same subject.

RULES YOU MUST FOLLOW:
1. NEVER copy sentences, phrases, or structure from the source.
   Rewrite all ideas entirely in your own voice.
2. Preserve factual accuracy. Do not invent statistics or quotes.
3. The output article must be at minimum 600 words.
4. Write for the target audience: general readers + search engines.
5. Use a clear structure: hook introduction, 3–5 body sections
   with H2 subheadings, and a strong conclusion with a CTA.
6. Always output valid JSON. No markdown outside the JSON block.
"""

USER_PROMPT_TEMPLATE = """
SOURCE ARTICLE:
Title: {original_title}
Published: {pub_date}
Source URL: {source_url}
Tags/Categories from feed: {source_tags}

Full article body:
---
{extracted_body}
---

TARGET WEBSITE CONTEXT:
Website name: {site_name}
Niche/Topic: {site_niche}
Target audience: {target_audience}
Tone of voice: {tone}

YOUR TASK:
Produce a new, 100% original article on this topic.
Return ONLY a JSON object in this exact structure:

{{
  "headline": "SEO-optimised title, 50–60 chars, includes primary keyword",
  "slug": "url-friendly-version-of-title",
  "meta_description": "150–160 char summary for Google search snippet",
  "focus_keyword": "single primary keyword this article targets",
  "secondary_keywords": ["keyword2", "keyword3", "keyword4"],
  "body_html": "<h2>...</h2><p>...</p>... full article in HTML",
  "excerpt": "2–3 sentence teaser for WordPress excerpt field",
  "suggested_categories": ["Category1", "Category2"],
  "suggested_tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "estimated_read_time": "X min read",
  "word_count": 750
}}
"""


def rewrite_article(article: Article) -> dict:
    """
    Call OpenRouter API to generate an editorial article from a source.
    Node 4 Specification: Understand context → rewrite → SEO optimize → plagiarism-free.
    Returns a dict with rewritten fields from JSON output.
    """
    api_key = Setting.get("ai_api_key")
    if not api_key:
        api_key = getattr(config, "OPENROUTER_API_KEY", None)
        
    if not api_key:
        _log("AI generation skipped — no API key configured", "warning")
        return {}

    model = Setting.get("ai_model", "openai/gpt-4o-mini")
    
    # If using a free model, we can try other free models as fallbacks.
    models_to_try = [model]
    if ":free" in model or "free" in model.lower():
        fallbacks = [
            "google/gemma-3-27b-it:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "nousresearch/hermes-3-llama-3.1-405b:free",
            "qwen/qwen3-next-80b-a3b-instruct:free",
            "mistralai/mistral-small-3.1-24b-instruct:free"
        ]
        for f in fallbacks:
            if f not in models_to_try:
                models_to_try.append(f)

    # Format the user prompt
    user_prompt = USER_PROMPT_TEMPLATE.format(
        original_title=article.original_title,
        pub_date=article.original_pub_date,
        source_url=article.source_url,
        source_tags=article.source_tags or "",
        extracted_body=article.extracted_body[:15000], 
        site_name=Setting.get("site_name", "Contexta"),
        site_niche=getattr(config, "SITE_NICHE", "Technology / AI"),
        target_audience=getattr(config, "TARGET_AUDIENCE", "tech-savvy professionals"),
        tone=getattr(config, "TONE", "authoritative but approachable")
    )

    last_error_msg = ""
    for current_model in models_to_try:
        try:
            payload = {
                "model": current_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ]
            }
            
            # Only add response_format for OpenAI models as it can break others on OpenRouter
            if "openai" in current_model.lower() or "gpt-4" in current_model.lower():
                payload["response_format"] = {"type": "json_object"}

            response = requests.post(
                url="https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://contexta.io", # Optional
                    "X-Title": "Contexta", # Optional
                },
                data=json.dumps(payload),
                timeout=120
            )

            if response.status_code != 200:
                error_msg = response.text
                try:
                    err_data = response.json()
                    if "error" in err_data:
                        base_msg = err_data["error"].get("message", "")
                        raw_msg = err_data["error"].get("metadata", {}).get("raw", "")
                        error_msg = f"{base_msg} - {raw_msg}" if raw_msg else base_msg
                except:
                    pass
                
                last_error_msg = error_msg
                
                # If rate limited (429) OR upstream error (502, 500) and we have more models, try the next
                if response.status_code in [429, 502, 500, 400] and current_model != models_to_try[-1]:
                    _log(f"Model {current_model} failed ({response.status_code}). Trying fallback...", "warning")
                    continue
                
                _log(f"OpenRouter API error: {response.status_code}", "error", error_msg)
                raise Exception(f"OpenRouter Error {response.status_code}: {error_msg}")

            result_json = response.json()
            raw_text = result_json['choices'][0]['message']['content']
            
            # Bulletproof JSON extraction: find first { and last }
            clean = raw_text.strip()
            start_idx = clean.find("{")
            end_idx = clean.rfind("}")
            
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                clean = clean[start_idx : end_idx + 1]
            
            try:
                rewritten = json.loads(clean)
                _log(f"AI rewrite complete for: {article.original_title[:40]} using {current_model}", "success")
                return rewritten
            except json.JSONDecodeError as e:
                _log(f"AI returned invalid JSON. Error: {e}", "error", f"Raw text preview: {raw_text[:500]}...")
                return {}

        except Exception as e:
            last_error_msg = str(e)
            if current_model != models_to_try[-1]:
                continue
            
            _log("OpenRouter API call failed", "error", str(e))
            return {}

    return {}


def list_available_models() -> tuple[dict, bool]:
    """Fetch available models from OpenRouter."""
    try:
        resp = requests.get("https://openrouter.ai/api/v1/models", timeout=5)
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            # Curate a few top ones
            favorites = ["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet", "google/gemini-flash-1.5"]
            recommended = []
            others = []
            for m in data:
                item = {"id": m["id"], "name": m["name"]}
                if m["id"] in favorites:
                    recommended.append(item)
                else:
                    others.append(item)
            return {"recommended": recommended, "others": others}, False
    except:
        pass

    # Fallback list
    fallback_models = [
        {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini (Fast & Cheap)"},
        {"id": "google/gemma-3-27b-it:free", "name": "Gemma 3 27B (Free Reliable)"},
        {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3 70B (Great Value)"},
    ]
    return {"recommended": fallback_models, "others": []}, True

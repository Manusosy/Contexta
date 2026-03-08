"""AI Service — generates editorial content via OpenRouter API."""
import requests
from models import Setting, db
from utils.logger import log_event as _log

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
APP_URL = "https://contexta.app"  # Sent as HTTP-Referer header

CONTEXT_PROMPT_TEMPLATE = """You are an expert news analyst.
Read the provided source article carefully.

Extract and summarize the core factual content, main talking points, tone, and pacing of the article.
Provide a clear, bulleted list of the essential information that MUST be included in a follow-up piece. Do NOT write an article yet, just extract the context.

Source Article:
---
{content}
"""

DRAFT_PROMPT_TEMPLATE = """You are an experienced news editor and journalist.

You will be given the content of a real published article. Study the tone, pacing, vocabulary, and narrative style of the article carefully.

Your task is to write a completely original follow-up editorial article inspired by the same topic. Do not summarize the article and do not rewrite sentences from it. Instead, produce a fresh piece that naturally expands on the subject, similar to how a newsroom would publish a related story or analysis.

The writing must closely match the tone and voice of the original article. Maintain a natural human writing rhythm that feels like it came from a professional editorial desk.

Requirements:

- Write in a confident, authoritative editorial tone.
- The article must read naturally and professionally, not like AI generated text.
- Avoid generic phrasing and avoid common AI writing patterns.
- Do not use dashes of any kind in the article.
- Do not mention that this article is based on another article.
- Do not repeat sentences or structure from the source content.
- Use clear paragraphs with logical progression of ideas.
- Provide insight, implications, or context that a journalist would add.
- Write between {word_count_min} and {word_count_target} words.
- Use clear section headings where appropriate.
- Keep the writing direct, informative, and engaging.

FORMATTING REQUIREMENTS:
- Your response MUST be valid HTML.
- **CRITICAL**: The very first element of your response MUST be a catchy, original, SEO-optimized title wrapped in an `<h1>` tag.
- Use `<h2>` and `<h3>` tags for section headings.
- Use `<p>` tags for all paragraphs.
- Do NOT wrap your response in markdown code blocks (e.g. ```html). Output pure HTML only.

{style_instructions}
{custom_prompt}

Source article content:

{context_points}

Now write the new editorial article."""


RELEVANCE_FILTER_PROMPT = """Analyze the following article snippet. 
Does it contain meaningful news, a story, or educational content? 
If it is spam, a simple link list, a weather report without narrative, or low-quality nonsense, answer 'NO'. 
Otherwise, if it is a valid article for editorial rewriting, answer 'YES'.

Snippet:
{snippet}

Answer (YES/NO):"""


def check_relevance(content: str) -> bool:
    """Uses AI to quickly determine if an article is worth processing."""
    api_key = Setting.get("ai_api_key")
    if not api_key:
        return True # Default to True if no key

    model = Setting.get("ai_model", "openai/gpt-4o-mini")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": APP_URL,
        "X-Title": "Contexta",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": RELEVANCE_FILTER_PROMPT.format(snippet=content[:1000])}],
        "temperature": 0.0,
        "max_tokens": 5,
    }

    try:
        response = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"].strip().upper()
        return "YES" in answer
    except Exception as e:
        _log("Relevance check failed, proceeding by default", "warning", str(e))
        return True


def generate_article(content: str, is_trial: bool = False) -> str:
    """
    Call OpenRouter API to generate an editorial article.
    Returns the generated HTML string, or empty string on failure.
    
    If is_trial is True, it enforces a 300-word limit and uses a free model.
    """
    api_key = Setting.get("ai_api_key")
    if not api_key:
        _log("AI generation skipped — no API key configured", "warning")
        return ""

    if is_trial:
        # Use trial-specific model or fallback to Gemini Flash Free
        model = Setting.get("ai_trial_model", "google/gemini-2.0-flash:free")
        temperature = 0.7
        max_tokens = 1000
    else:
        # Premium logic
        model = Setting.get("ai_model", "openai/gpt-4o-mini")
        
        # Smart Selection / Auto Model Logic
        if model == "auto":
            # Select best model for premium editorial work
            model = "openai/gpt-4o"
            
        temperature = float(Setting.get("ai_temperature", "0.7"))
        max_tokens = int(Setting.get("ai_max_tokens", "2000"))

    # Step 1: Context Extraction
    context_prompt = CONTEXT_PROMPT_TEMPLATE.format(content=content[:4000])
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": APP_URL,
        "X-Title": "Contexta",
        "Content-Type": "application/json",
    }
    
    context_payload = {
        "model": model,
        "messages": [{"role": "user", "content": context_prompt}],
        "temperature": 0.3, # Lower temperature for facts
        "max_tokens": 1000,
    }

    try:
        response = requests.post(OPENROUTER_URL, json=context_payload, headers=headers, timeout=120)
        response.raise_for_status()
        context_data = response.json()
        extracted_context = context_data["choices"][0]["message"]["content"].strip()
        _log(f"AI context extraction complete", "info")
    except Exception as e:
        _log("AI context extraction failed", "error", str(e))
        return ""

    # Step 2: Article Drafting
    # Build style modifiers
    style_parts = []
    if Setting.get("ai_style_instructions"):
        style_parts.append(Setting.get("ai_style_instructions"))
    if Setting.get("ai_preserve_tone") == "true":
        style_parts.append("Preserve the original article's tone.")
    if Setting.get("ai_avoid_generic") == "true":
        style_parts.append("Avoid generic AI phrasing.")
    if Setting.get("ai_no_long_dashes") == "true":
        style_parts.append("Do not use em dashes or long dashes.")
    if Setting.get("ai_regional_insight") == "true":
        style_parts.append("Add relevant regional context and insight where appropriate.")

    style_instructions = "\n".join(style_parts)
    
    if is_trial:
        word_count_min = "200"
        word_count_target = "300"
    else:
        # Journalistic guidelines: 800 - 1200 words
        word_count_min = Setting.get("ai_word_count_min", "800")
        word_count_target = Setting.get("ai_word_count_target", "1200")
    
    custom_prompt_raw = Setting.get("ai_custom_prompt", "")
    custom_prompt = f"USER CUSTOM INSTRUCTIONS:\n{custom_prompt_raw}" if custom_prompt_raw else ""

    draft_prompt = DRAFT_PROMPT_TEMPLATE.format(
        word_count_min=word_count_min,
        word_count_target=word_count_target,
        style_instructions=style_instructions,
        custom_prompt=custom_prompt,
        context_points=extracted_context
    )

    draft_payload = {
        "model": model,
        "messages": [{"role": "user", "content": draft_prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        response = requests.post(OPENROUTER_URL, json=draft_payload, headers=headers, timeout=120)
        response.raise_for_status()
        data = response.json()
        generated = data["choices"][0]["message"]["content"].strip()
        _log(f"AI generation complete — model: {model}", "success", f"{len(generated)} chars")
        return generated
    except Exception as e:
        _log("AI generation failed", "error", str(e))
        return ""


def list_available_models() -> tuple[dict, bool]:
    """Fetch available models from OpenRouter (best-effort). Returns {recommended: [], others: []}, fallback_used."""
    curated = _default_models()
    curated_ids = {m["id"] for m in curated}
    
    api_key = Setting.get("ai_api_key")
    if not api_key:
        return {"recommended": curated, "others": []}, True
        
    try:
        resp = requests.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        
        # Add models from API that are not in our curated list
        api_models = []
        for m in data:
            mid = m["id"]
            if mid not in curated_ids:
                name = m.get("name", mid)
                if mid.endswith(":free") and "(Free)" not in name:
                    name += " (Free)"
                api_models.append({"id": mid, "name": name})
        
        # Return grouped data
        return {"recommended": curated, "others": api_models}, False
    except Exception:
        return {"recommended": curated, "others": []}, True


def _default_models() -> list[dict]:
    return [
        # --- PREMIUM TOOLS ---
        {"id": "auto", "name": "✨ Smart Selection (Auto-Select Best Model)"},
        
        # --- FREE MODELS (Prioritized for Writing/SEO) ---
        {"id": "google/gemini-2.0-flash:free", "name": "Gemini 2.0 Flash (Free) - Fast & Modern"},
        {"id": "google/gemini-2.0-pro-exp-02-05:free", "name": "Gemini 2.0 Pro (Free) - High Quality"},
        {"id": "deepseek/deepseek-r1:free", "name": "DeepSeek R1 (Free) - Great Reasoning"},
        {"id": "mistralai/mistral-7b-instruct:free", "name": "Mistral 7B Instruct (Free)"},
        {"id": "mistralai/pixtral-12b:free", "name": "Pixtral 12B (Free)"},
        {"id": "microsoft/phi-3-medium-128k-instruct:free", "name": "Phi-3 Medium (Free)"},
        {"id": "qwen/qwen-2-72b-instruct:free", "name": "Qwen 2 72B (Free)"},
        {"id": "meta-llama/llama-3-8b-instruct:free", "name": "Llama 3 8B (Free)"},
        
        # --- TOP-TIER PAID MODELS (SEO & Professional) ---
        {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini (Best for SEO & Speed)"},
        {"id": "openai/gpt-4o", "name": "GPT-4o (Professional & Reliable)"},
        {"id": "anthropic/claude-3.5-sonnet", "name": "Claude 3.5 Sonnet (Premium/Creative)"},
        {"id": "anthropic/claude-3-haiku", "name": "Claude 3 Haiku (Fast/Affordable)"},
        {"id": "google/gemini-pro-1.5", "name": "Gemini 1.5 Pro (Large Context)"},
        {"id": "mistralai/mistral-large", "name": "Mistral Large (High Quality)"},
        {"id": "deepseek/deepseek-chat", "name": "DeepSeek V3 (Competitive Paid)"},
        {"id": "meta-llama/llama-3.1-405b", "name": "Llama 3.1 405B (Powerhouse)"},
    ]

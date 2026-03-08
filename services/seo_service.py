"""SEO Service — extracts keywords, generates meta, slug, and SEO score."""
import re
import math
import json
from collections import Counter
from bs4 import BeautifulSoup
from models import Setting


STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "was", "are", "were", "be", "been",
    "has", "have", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "this", "that", "these", "those",
    "it", "its", "as", "up", "if", "so", "no", "not", "than", "then",
    "also", "more", "most", "about", "which", "who", "what", "when",
    "where", "how", "why", "into", "over", "after", "before", "between",
    "just", "can", "said", "says", "i", "we", "he", "she", "they",
}


def process_article(content_html: str, original_title: str = "") -> dict:
    """
    Run full SEO processing on generated HTML content.
    Returns dict with: primary_keyword, seo_title, meta_description, slug, seo_score, word_count.
    """
    soup = BeautifulSoup(content_html, "lxml")
    
    # Extract AI-generated title from <h1>
    h1_tag = soup.find("h1")
    if h1_tag:
        seo_title = h1_tag.get_text(strip=True)
        h1_tag.decompose()  # Remove it from the content body so it's not duplicated
        content_html = str(soup.body) if soup.body else str(soup) # Keep the rest as content
    else:
        seo_title = original_title

    plain_text = soup.get_text(separator=" ", strip=True)
    words = _tokenize(plain_text)

    primary_keyword = _extract_keyword(words)
    meta_length = int(Setting.get("seo_meta_length", "160"))
    meta_description = _generate_meta(plain_text, meta_length)
    auto_slug = Setting.get("seo_auto_slug", "true") == "true"
    slug = _generate_slug(seo_title) if auto_slug else ""
    word_count = len(words)
    seo_score = _calculate_seo_score(
        plain_text=plain_text,
        word_count=word_count,
        primary_keyword=primary_keyword,
        has_h2=bool(soup.find("h2")),
        has_meta=bool(meta_description),
        slug=slug,
    )

    if Setting.get("seo_faq_schema") == "true":
        faq_schema = _generate_faq_schema(plain_text)
        if faq_schema:
            content_html += f"\n<script type=\"application/ld+json\">\n{faq_schema}\n</script>"

    return {
        "primary_keyword": primary_keyword,
        "seo_title": seo_title,
        "content_html": content_html,
        "meta_description": meta_description,
        "slug": slug,
        "seo_score": seo_score,
        "word_count": word_count,
    }


def _tokenize(text: str) -> list[str]:
    """Lowercase tokenizer stripping punctuation."""
    return [
        w.lower() for w in re.findall(r"\b[a-zA-Z]{3,}\b", text)
        if w.lower() not in STOP_WORDS
    ]


def _extract_keyword(words: list[str]) -> str:
    """Simple TF-IDF-inspired top-1 keyword extraction."""
    if not words:
        return ""
    freq = Counter(words)
    # Weighted by log-frequency (serves as TF proxy)
    scored = {w: freq[w] * math.log(1 + freq[w]) for w in freq}
    top = sorted(scored, key=scored.get, reverse=True)
    return top[0] if top else ""


def _generate_meta(text: str, max_length: int = 160) -> str:
    """Generate meta description from first meaningful sentence."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    description = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) > 30:
            description = sentence
            break
    if len(description) > max_length:
        description = description[:max_length - 3] + "..."
    return description


def _generate_slug(text: str) -> str:
    """Convert text to URL-friendly slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    slug = slug.strip("-")
    words = slug.split("-")
    return "-".join(words[:8])  # Max 8 words in slug


def _generate_faq_schema(text: str) -> str:
    """Extract question-answer pairs and generate FAQPage JSON-LD schema."""
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    faqs = []
    
    for i in range(len(sentences) - 1):
        if sentences[i].endswith("?") and not sentences[i+1].endswith("?"):
            question = sentences[i]
            answer = sentences[i+1]
            if len(question) > 15 and len(answer) > 20:
                faqs.append({
                    "@type": "Question",
                    "name": question,
                    "acceptedAnswer": {
                        "@type": "Answer",
                        "text": answer
                    }
                })
                
    if not faqs:
        return ""
        
    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": faqs[:5]  # Limit to top 5 FAQs
    }
    return json.dumps(schema, indent=2)


def _calculate_seo_score(
    plain_text: str,
    word_count: int,
    primary_keyword: str,
    has_h2: bool,
    has_meta: bool,
    slug: str,
) -> int:
    """
    Calculate SEO score out of 100.
    Weighted criteria:
      - Word count 800-1200: 25 pts
      - Keyword in first 100 words: 20 pts
      - H2 headings present: 20 pts
      - Meta description present: 20 pts
      - Slug present and clean: 15 pts
    """
    score = 0

    target = int(Setting.get("ai_word_count_target", "600"))
    
    # Word count
    if (target - 200) <= word_count <= (target + 400):
        score += 25
    elif (target - 400) <= word_count < (target - 200) or (target + 400) < word_count <= (target + 600):
        score += 15
    elif word_count > target // 2:
        score += 8

    # Keyword in first 100 words
    first_100 = " ".join(plain_text.split()[:100]).lower()
    if primary_keyword and primary_keyword in first_100:
        score += 20

    # H2 headings
    if has_h2:
        score += 20

    # Meta description
    if has_meta:
        score += 20

    # Slug
    if slug:
        score += 15

    return min(score, 100)

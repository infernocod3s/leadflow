"""Shared structured data extractors — JSON-LD, OpenGraph, meta tags, tech detection."""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from growthpal.utils.logger import get_logger

log = get_logger(__name__)


# ── JSON-LD Extraction ──────────────────────────────────────────────────────


def extract_json_ld(html: str) -> list[dict]:
    """Extract all JSON-LD objects from HTML. ~41% of websites have these."""
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            text = script.string or ""
            data = json.loads(text)
            if isinstance(data, list):
                results.extend(data)
            elif isinstance(data, dict):
                results.append(data)
        except (json.JSONDecodeError, TypeError):
            continue

    return results


def extract_organization_from_json_ld(json_ld_items: list[dict]) -> dict[str, Any]:
    """Extract organization data from JSON-LD objects.

    Returns dict with: company_name, description, employee_count, industry, social_links, etc.
    """
    result: dict[str, Any] = {}

    for item in json_ld_items:
        item_type = item.get("@type", "")
        if isinstance(item_type, list):
            item_type = item_type[0] if item_type else ""

        if item_type in ("Organization", "Corporation", "LocalBusiness", "Company"):
            result["company_name"] = item.get("name", "")
            result["description"] = item.get("description", "")

            # Employee count
            employees = item.get("numberOfEmployees")
            if isinstance(employees, dict):
                result["employee_count"] = employees.get("value", "")
            elif employees:
                result["employee_count"] = str(employees)

            result["industry"] = item.get("industry", "")

            # Social links
            same_as = item.get("sameAs", [])
            if isinstance(same_as, str):
                same_as = [same_as]
            social = {}
            for url in same_as:
                if "linkedin.com" in url:
                    social["linkedin"] = url
                elif "twitter.com" in url or "x.com" in url:
                    social["twitter"] = url
                elif "facebook.com" in url:
                    social["facebook"] = url
                elif "github.com" in url:
                    social["github"] = url
                elif "youtube.com" in url:
                    social["youtube"] = url
            if social:
                result["social_links"] = social

            result["founding_date"] = item.get("foundingDate", "")
            result["address"] = item.get("address", {})
            break

        elif item_type == "WebSite":
            if not result.get("company_name"):
                result["company_name"] = item.get("name", "")

        elif item_type == "Product":
            products = result.get("products", [])
            products.append({
                "name": item.get("name", ""),
                "description": item.get("description", ""),
            })
            result["products"] = products

    return result


# ── OpenGraph & Meta Tags ───────────────────────────────────────────────────


def extract_opengraph(html: str) -> dict[str, str]:
    """Extract OpenGraph meta tags from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    og: dict[str, str] = {}

    for meta in soup.find_all("meta"):
        prop = meta.get("property", "") or meta.get("name", "")
        content = meta.get("content", "")
        if prop.startswith("og:") and content:
            og[prop[3:]] = content

    return og


def extract_meta_tags(html: str) -> dict[str, str]:
    """Extract useful meta tags (description, keywords, etc.)."""
    soup = BeautifulSoup(html, "html.parser")
    meta_data: dict[str, str] = {}

    for meta in soup.find_all("meta"):
        name = (meta.get("name") or meta.get("property") or "").lower()
        content = meta.get("content", "")
        if name in ("description", "keywords", "author", "application-name") and content:
            meta_data[name] = content

    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        meta_data["title"] = title_tag.string.strip()

    return meta_data


# ── Tech Stack Detection ────────────────────────────────────────────────────

# Patterns: (tech_name, regex_pattern_for_html_or_headers)
TECH_PATTERNS = [
    # CMS
    ("WordPress", r'wp-content|wp-includes|wordpress', "cms"),
    ("Shopify", r'cdn\.shopify\.com|Shopify\.theme', "cms"),
    ("Webflow", r'webflow\.com|wf-', "cms"),
    ("Squarespace", r'squarespace\.com|sqsp', "cms"),
    ("Wix", r'wix\.com|wixsite', "cms"),
    ("Ghost", r'ghost\.org|ghost-', "cms"),
    ("Drupal", r'drupal\.org|drupal\.js', "cms"),
    # Frameworks
    ("React", r'react\.production|__NEXT_DATA__|_next/', "framework"),
    ("Next.js", r'__NEXT_DATA__|_next/', "framework"),
    ("Vue.js", r'vue\.min\.js|vue\.runtime|__VUE__', "framework"),
    ("Angular", r'ng-version|angular\.min\.js', "framework"),
    ("Gatsby", r'gatsby-', "framework"),
    # Analytics
    ("Google Analytics", r'google-analytics\.com|gtag|GA_MEASUREMENT_ID', "analytics"),
    ("Segment", r'segment\.com/analytics|analytics\.min\.js', "analytics"),
    ("Mixpanel", r'mixpanel\.com|mixpanel\.init', "analytics"),
    ("Hotjar", r'hotjar\.com|_hjSettings', "analytics"),
    ("HubSpot", r'hs-scripts\.com|hubspot\.com|hbspt', "analytics"),
    # Chat / Support
    ("Intercom", r'intercom\.com|intercomSettings', "chat"),
    ("Drift", r'drift\.com|driftt', "chat"),
    ("Zendesk", r'zendesk\.com|zdassets', "chat"),
    ("Crisp", r'crisp\.chat', "chat"),
    # Email
    ("Mailchimp", r'mailchimp\.com|mc\.js', "email"),
    ("SendGrid", r'sendgrid\.net', "email"),
    # Infrastructure
    ("Cloudflare", r'cloudflare', "hosting"),
    ("AWS", r'amazonaws\.com|aws-', "hosting"),
    ("Vercel", r'vercel\.app|vercel-', "hosting"),
    ("Netlify", r'netlify\.app|netlify', "hosting"),
    ("Heroku", r'herokuapp\.com', "hosting"),
]


def extract_tech_from_html(html: str, headers: dict[str, str] | None = None) -> dict[str, list[str]]:
    """Detect tech stack from HTML content and HTTP headers.

    Returns dict with keys: cms, framework, analytics, chat, email, hosting
    """
    tech: dict[str, list[str]] = {}
    combined = html.lower()

    if headers:
        header_str = " ".join(f"{k}: {v}" for k, v in headers.items()).lower()
        combined += " " + header_str

        # Check server header
        server = headers.get("server", "").lower()
        if "cloudflare" in server:
            tech.setdefault("hosting", []).append("Cloudflare")
        elif "nginx" in server:
            tech.setdefault("hosting", []).append("Nginx")
        elif "apache" in server:
            tech.setdefault("hosting", []).append("Apache")

    for name, pattern, category in TECH_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            if name not in tech.get(category, []):
                tech.setdefault(category, []).append(name)

    return tech


def detect_email_provider(mx_records: list[str]) -> str | None:
    """Detect email provider from MX records."""
    mx_lower = " ".join(mx_records).lower()

    providers = [
        ("Google Workspace", ["google.com", "googlemail.com", "aspmx"]),
        ("Microsoft 365", ["outlook.com", "microsoft.com", "office365"]),
        ("Zoho", ["zoho.com"]),
        ("ProtonMail", ["protonmail.ch", "proton.me"]),
        ("Fastmail", ["fastmail.com"]),
        ("Mimecast", ["mimecast.com"]),
        ("Barracuda", ["barracudanetworks.com"]),
    ]

    for provider, patterns in providers:
        if any(p in mx_lower for p in patterns):
            return provider

    return None


# ── Data Quality Scoring ────────────────────────────────────────────────────

# Field weights for quality scoring (total = 1.0)
QUALITY_WEIGHTS = {
    "company_name": 0.15,
    "description": 0.20,
    "industry": 0.15,
    "employee_count": 0.10,
    "tech_stack": 0.10,
    "products": 0.10,
    "social_links": 0.05,
    "email_provider": 0.05,
    "funding": 0.05,
    "target_market": 0.05,
}


def compute_data_quality_score(data: dict[str, Any]) -> float:
    """Compute data quality score from 0.0 to 1.0 based on field completeness.

    Uses weighted scoring based on field importance for B2B lead enrichment.
    """
    score = 0.0

    for field, weight in QUALITY_WEIGHTS.items():
        value = data.get(field)
        if value:
            if isinstance(value, str) and len(value) > 3:
                score += weight
            elif isinstance(value, (list, dict)) and len(value) > 0:
                score += weight
            elif isinstance(value, (int, float)) and value > 0:
                score += weight

    return round(min(score, 1.0), 3)

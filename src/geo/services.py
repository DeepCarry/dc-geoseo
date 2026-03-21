from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .utils import domain_from_url, ensure_url, now_date, safe_name, score_label


def technical_score(page_data: dict, robots_data: dict) -> int:
    score = 100
    if not page_data.get("title"):
        score -= 8
    if not page_data.get("description"):
        score -= 8
    if not page_data.get("canonical"):
        score -= 5
    if not page_data.get("has_ssr_content", True):
        score -= 25
    if page_data.get("status_code") and page_data.get("status_code") >= 400:
        score -= 20

    security_headers = page_data.get("security_headers", {})
    for h in [
        "Strict-Transport-Security",
        "Content-Security-Policy",
        "X-Frame-Options",
        "X-Content-Type-Options",
        "Referrer-Policy",
    ]:
        if not security_headers.get(h):
            score -= 4

    blocked_critical = 0
    crawler_status = robots_data.get("ai_crawler_status", {})
    for key in ["GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended"]:
        st = (crawler_status.get(key) or "").upper()
        if "BLOCK" in st:
            blocked_critical += 1
    score -= blocked_critical * 5
    return max(0, min(100, score))


def schema_score(page_data: dict) -> int:
    structured = page_data.get("structured_data", [])
    if not structured:
        return 10

    score = 40
    schema_types = []
    for block in structured:
        if isinstance(block, dict):
            t = block.get("@type")
            if isinstance(t, list):
                schema_types.extend(t)
            elif t:
                schema_types.append(t)

    types_l = {str(t).lower() for t in schema_types}
    if any("organization" in t for t in types_l):
        score += 20
    if any(t in types_l for t in ["article", "blogposting", "newsarticle"]):
        score += 15
    if any("website" in t for t in types_l):
        score += 10
    if any("product" in t for t in types_l):
        score += 10
    return max(0, min(100, score))


def content_score(page_data: dict, citability_data: dict) -> int:
    words = page_data.get("word_count", 0)
    headings = len(page_data.get("heading_structure", []))
    internal_links = len(page_data.get("internal_links", []))
    base = 25

    if words >= 1200:
        base += 20
    elif words >= 700:
        base += 14
    elif words >= 300:
        base += 8

    if headings >= 6:
        base += 10
    elif headings >= 3:
        base += 6

    if internal_links >= 5:
        base += 6

    citability = int(citability_data.get("average_citability_score", 0) or 0)
    base += int(citability * 0.4)
    return max(0, min(100, base))


def platform_scores(tech: int, content: int, citability: int, brand: int, schema: int) -> dict:
    return {
        "Google AI Overviews": max(0, min(100, int((tech * 0.30) + (schema * 0.25) + (content * 0.25) + (citability * 0.20)))),
        "ChatGPT": max(0, min(100, int((citability * 0.35) + (brand * 0.30) + (tech * 0.20) + (schema * 0.15)))),
        "Perplexity": max(0, min(100, int((citability * 0.35) + (brand * 0.35) + (tech * 0.20) + (schema * 0.10)))),
        "Gemini": max(0, min(100, int((tech * 0.30) + (schema * 0.25) + (content * 0.25) + (brand * 0.20)))),
        "Bing Copilot": max(0, min(100, int((tech * 0.30) + (brand * 0.30) + (content * 0.20) + (schema * 0.20)))),
    }


def infer_brand_name(page_data: dict, url: str) -> str:
    title = (page_data.get("title") or "").strip()
    if title:
        for sep in ["|", "-", "—", "::"]:
            if sep in title:
                return title.split(sep)[0].strip()
        return title[:60]
    return domain_from_url(url).split(":")[0]


def compute_brand_score(brand_report: dict) -> int:
    score = 15
    wiki = brand_report.get("platforms", {}).get("wikipedia", {})
    if wiki.get("has_wikipedia_page"):
        score += 30
    if wiki.get("has_wikidata_entry"):
        score += 15
    score += 15  # baseline for scan availability
    return max(0, min(100, score))


def run_audit(url: str) -> dict:
    from scripts.brand_scanner import generate_brand_report
    from scripts.citability_scorer import analyze_page_citability
    from scripts.fetch_page import fetch_page, fetch_robots_txt
    from scripts.llmstxt_generator import validate_llmstxt

    url = ensure_url(url)
    page = fetch_page(url)
    robots = fetch_robots_txt(url)
    llms = validate_llmstxt(url)
    cit = analyze_page_citability(url)

    brand_name = infer_brand_name(page, url)
    brand_report = generate_brand_report(brand_name, domain_from_url(url))

    citability = int(cit.get("average_citability_score", 0) or 0)
    tech = technical_score(page, robots)
    schema = schema_score(page)
    content = content_score(page, cit)
    brand = compute_brand_score(brand_report)
    llms_score = 0
    if llms.get("exists"):
        llms_score = 50 if llms.get("format_valid") else 30
        if llms.get("full_version", {}).get("exists"):
            llms_score += 20

    platforms = platform_scores(tech, content, citability, brand, schema)
    platform_opt = int(sum(platforms.values()) / len(platforms))

    geo_score = int(
        (citability * 0.25)
        + (brand * 0.20)
        + (content * 0.20)
        + (tech * 0.15)
        + (schema * 0.10)
        + (platform_opt * 0.10)
    )

    findings = []
    if not page.get("has_ssr_content", True):
        findings.append({"severity": "critical", "title": "Possible CSR-only rendering", "description": "Main app root appears to have minimal server-rendered content."})
    if not page.get("structured_data"):
        findings.append({"severity": "high", "title": "No JSON-LD schema detected", "description": "Add Organization/Article/Product schema based on business type."})
    if not llms.get("exists"):
        findings.append({"severity": "medium", "title": "No llms.txt detected", "description": "Create /llms.txt and optionally /llms-full.txt for AI discoverability."})
    blocked = [k for k, v in (robots.get("ai_crawler_status") or {}).items() if "BLOCK" in (v or "").upper()]
    if blocked:
        findings.append({"severity": "critical", "title": "AI crawler blocking detected", "description": f"Blocked or restricted crawlers: {', '.join(blocked[:8])}."})

    quick_wins = [
        {"action": "Allow GPTBot, ClaudeBot, PerplexityBot in robots.txt", "impact": "Unlock AI crawler access"},
        {"action": "Add Organization schema with sameAs links", "impact": "Improve entity recognition"},
        {"action": "Publish llms.txt and llms-full.txt", "impact": "Improve AI content discovery"},
    ]

    return {
        "url": url,
        "brand_name": brand_name,
        "date": now_date(),
        "geo_score": geo_score,
        "scores": {
            "ai_citability": citability,
            "brand_authority": brand,
            "content_eeat": content,
            "technical": tech,
            "schema": schema,
            "platform_optimization": platform_opt,
            "llms": llms_score,
        },
        "platforms": platforms,
        "executive_summary": f"{brand_name} currently scores {geo_score}/100 ({score_label(geo_score)}). Priorities: crawler access, schema coverage, and citation-ready content blocks.",
        "findings": findings,
        "quick_wins": quick_wins,
        "medium_term": [
            {"action": "Rewrite top pages into Q&A blocks (134-167 words)", "impact": "Increase citability"},
            {"action": "Expand sameAs profiles across major platforms", "impact": "Increase brand authority"},
        ],
        "strategic": [
            {"action": "Publish original data/case studies", "impact": "Higher citation likelihood"},
            {"action": "Build recurring content + platform presence", "impact": "Long-term GEO growth"},
        ],
        "crawler_access": {
            k: {"platform": "AI", "status": v, "recommendation": "Allow for visibility" if "BLOCK" in (v or "").upper() else "Keep allowed"}
            for k, v in (robots.get("ai_crawler_status") or {}).items()
        },
        "raw": {
            "page": page,
            "robots": robots,
            "llms": llms,
            "citability": cit,
            "brand": brand_report,
        },
    }


def render_report_md(audit: dict) -> str:
    s = audit["scores"]
    lines = [
        f"# GEO Client Report — {audit['brand_name']}",
        f"\nDate: {audit['date']}  ",
        f"Domain: {audit['url']}\n",
        f"## GEO Readiness Score: {audit['geo_score']}/100 — {score_label(audit['geo_score'])}\n",
        "## Score Breakdown",
        "| Component | Score |",
        "|---|---|",
        f"| AI Citability | {s['ai_citability']}/100 |",
        f"| Brand Authority | {s['brand_authority']}/100 |",
        f"| Content E-E-A-T | {s['content_eeat']}/100 |",
        f"| Technical | {s['technical']}/100 |",
        f"| Schema | {s['schema']}/100 |",
        f"| Platform Optimization | {s['platform_optimization']}/100 |",
        "\n## AI Platform Readiness",
        "| Platform | Score |",
        "|---|---|",
    ]
    for p, v in audit["platforms"].items():
        lines.append(f"| {p} | {v}/100 |")

    lines.append("\n## Findings")
    for f in audit.get("findings", []):
        lines.append(f"- **[{f.get('severity', 'info').upper()}]** {f.get('title')}: {f.get('description')}")

    lines.append("\n## Quick Wins")
    for idx, a in enumerate(audit.get("quick_wins", []), start=1):
        if isinstance(a, dict):
            lines.append(f"{idx}. {a.get('action')} — {a.get('impact')}")
        else:
            lines.append(f"{idx}. {a}")

    lines.append("\n## Executive Summary")
    lines.append(audit.get("executive_summary", ""))
    return "\n".join(lines) + "\n"


def save_audit_artifacts(audit: dict, out_dir: Path | None = None) -> dict[str, Path]:
    out_dir = out_dir or Path.cwd()
    domain = safe_name(domain_from_url(audit["url"]))
    date = audit.get("date") or now_date()

    audit_json = out_dir / f"{domain}-audit-{date}.json"
    report_md = out_dir / f"{domain}-geo-client-report-{date}.md"

    with open(audit_json, "w", encoding="utf-8") as f:
        json.dump(audit, f, indent=2, ensure_ascii=False)

    with open(report_md, "w", encoding="utf-8") as f:
        f.write(render_report_md(audit))

    return {"audit_json": audit_json, "report_md": report_md}


def generate_llms(url: str, full: bool = False) -> dict:
    from scripts.llmstxt_generator import generate_llmstxt

    data = generate_llmstxt(ensure_url(url))
    return {"content": data["generated_llmstxt_full"] if full else data["generated_llmstxt"], "meta": data}


def run_pdf(data_or_path: str, output: str | None = None) -> str:
    from scripts.generate_pdf_report import generate_report as generate_pdf

    output = output or "GEO-REPORT.pdf"
    if data_or_path.startswith("http://") or data_or_path.startswith("https://"):
        data = run_audit(data_or_path)
        generate_pdf(data, output)
        return output

    p = Path(data_or_path)
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    generate_pdf(data, output)
    return output


def prospects_path() -> Path:
    return Path.home() / ".geo-prospects" / "prospects.json"


def load_prospects() -> list[dict[str, Any]]:
    p = prospects_path()
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_prospects(items: list[dict[str, Any]]) -> None:
    p = prospects_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)


def find_prospect(items: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    key_l = key.lower()
    for it in items:
        if it.get("id", "").lower() == key_l or it.get("domain", "").lower() == key_l:
            return it
    return None


def generate_proposal_md(prospect: dict, lang: str = "zh") -> str:
    company = prospect.get("company") or prospect.get("domain")
    score = prospect.get("geo_score", 0)
    mrr = prospect.get("monthly_value", 5000)
    if lang == "en":
        return f"""# GEO Growth Proposal — {company}

## Executive Summary
{company} currently holds a GEO readiness score of **{score}/100**. This proposal outlines a six-month engagement focused on improving discoverability across ChatGPT, Gemini, Perplexity, Bing Copilot, and Google AI experiences.

## Recommended Engagement
- Recommended plan: GEO Growth Retainer
- Monthly investment: EUR {mrr}
- Initial term: 6 months

## Delivery Roadmap
1. Month 1: unblock crawler access, strengthen schema coverage, and publish llms.txt guidance
2. Month 2-3: rewrite priority pages into citation-ready blocks and improve E-E-A-T signals
3. Month 4-6: expand authority assets, original proof, and platform-specific optimization

## Expected Outcomes
- Stronger visibility in AI-generated answers
- Better structured content for citation and retrieval
- Clearer monthly reporting on GEO score movement and execution progress
"""
    return f"""# GEO 增长提案 — {company}

## 执行摘要
{company} 当前 GEO 就绪度为 **{score}/100**。本提案建议以 6 个月为周期，系统提升在 ChatGPT、Gemini、Perplexity、Bing Copilot 与 Google AI 场景下的可见度与引用机会。

## 建议合作方式
- 推荐方案：GEO 增长顾问
- 月度投入：EUR {mrr}
- 建议周期：6 个月

## 交付路线图
1. 第 1 个月：打通 crawler 可访问性、补齐结构化数据、发布 llms.txt
2. 第 2-3 个月：重写重点页面为可引用内容块，提升 E-E-A-T 信号
3. 第 4-6 个月：扩展品牌权威资产、原创证据与平台专项优化

## 预期结果
- 提升 AI 回答场景中的品牌可见度
- 提高页面被模型检索与引用的概率
- 建立可持续的月度 GEO 复盘与改进机制
"""


def generate_compare_md(baseline: dict, current: dict, company: str) -> str:
    b = baseline.get("geo_score", 0)
    c = current.get("geo_score", 0)
    d = c - b
    trend = "▲" if d > 0 else ("▼" if d < 0 else "──")
    return f"""# GEO Monthly Progress Report — {company}

- Baseline: {b}/100
- Current: {c}/100
- Change: {trend} {d:+d}

## Summary
Progress from previous audit to latest audit has been measured with the unified GEO model.
"""

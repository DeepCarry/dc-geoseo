#!/usr/bin/env python3
"""GEO Workspace Web UI (Flask + HTMX)."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, abort, render_template, request, send_file, session

ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from geo.auth import detect_codex
from geo.services import (
    find_prospect,
    generate_compare_md,
    generate_llms,
    generate_proposal_md,
    load_prospects,
    render_report_md,
    run_audit,
    run_pdf,
    save_audit_artifacts,
    save_prospects,
)
from geo.utils import domain_from_url, ensure_url, now_date, safe_name, score_label

app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = os.environ.get("GEO_WEBAPP_SECRET", "geo-workspace-dev")

CRM_PATH = Path.home() / ".geo-prospects" / "prospects.json"
AUDITS_DIR = Path.home() / ".geo-prospects" / "audits"
REPORTS_DIR = Path.home() / ".geo-prospects" / "reports"
PROPOSALS_DIR = Path.home() / ".geo-prospects" / "proposals"
LLMS_DIR = Path.home() / ".geo-prospects" / "llms"

for directory in [CRM_PATH.parent, AUDITS_DIR, REPORTS_DIR, PROPOSALS_DIR, LLMS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

LANGS = {"zh", "en"}

STATUS_META = {
    "lead": {"label": {"zh": "待跟进", "en": "Lead"}, "tone": "neutral"},
    "contacted": {"label": {"zh": "已联系", "en": "Contacted"}, "tone": "info"},
    "proposal": {"label": {"zh": "已提案", "en": "Proposal"}, "tone": "accent"},
    "won": {"label": {"zh": "已成交", "en": "Won"}, "tone": "success"},
    "lost": {"label": {"zh": "已丢失", "en": "Lost"}, "tone": "danger"},
}

TAB_META = [
    ("workspace", {"zh": "工作区", "en": "Workspace"}),
    ("audit", {"zh": "审计", "en": "Audit"}),
    ("reports", {"zh": "报告", "en": "Reports"}),
    ("prospects", {"zh": "线索", "en": "Prospects"}),
    ("proposal", {"zh": "提案", "en": "Proposal"}),
    ("compare", {"zh": "对比", "en": "Compare"}),
]


def current_lang() -> str:
    lang = _session_get("lang", "zh")
    return lang if lang in LANGS else "zh"


def L(zh: str, en: str) -> str:
    return zh if current_lang() == "zh" else en


def localize_env_message(message: str) -> str:
    if current_lang() == "en":
        return message
    message_l = (message or "").lower()
    if "not found in path" in message_l:
        return "未在 PATH 中找到 codex CLI。"
    if "not logged in" in message_l:
        return "已检测到 codex CLI，但尚未登录。"
    if "login status could not be verified" in message_l:
        return "检测到 codex CLI，但无法确认登录状态。请先执行 `codex login`。"
    return message


@app.context_processor
def inject_now() -> dict[str, Any]:
    return {
        "now": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "current_lang": current_lang(),
        "L": L,
    }


@app.template_filter("score_tier")
def score_tier(score: int) -> str:
    if score >= 80:
        return "good"
    if score >= 60:
        return "moderate"
    if score >= 40:
        return "poor"
    return "critical"


@app.template_filter("score_label")
def score_label_filter(score: int) -> str:
    return score_label(score)


@app.template_filter("money")
def money(value: Any) -> str:
    if not value:
        return "--"
    return f"EUR {int(value):,}".replace(",", " ")


@app.template_filter("status_meta")
def status_meta_filter(status: str) -> dict[str, str]:
    lang = current_lang()
    meta = STATUS_META.get(status)
    if not meta:
        return {"label": status or ("Unknown" if lang == "en" else "未知"), "tone": "neutral"}
    return {"label": meta["label"][lang], "tone": meta["tone"]}


@app.template_filter("basename")
def basename_filter(path: str) -> str:
    return Path(path).name if path else ""


@app.template_filter("pretty_json")
def pretty_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


@app.template_filter("datetime_short")
def datetime_short(value: str | None) -> str:
    if not value:
        return "--"
    return value.replace("T", " ")[:16]


@app.template_filter("download_href")
def download_href_filter(path: str | None) -> str | None:
    return download_href(path)


# Helpers

def _session_get(key: str, default: Any = None) -> Any:
    return session.get(key, default)


def _session_set(key: str, value: Any) -> None:
    session[key] = value
    session.modified = True


def add_log(message: str, level: str = "info") -> None:
    logs = _session_get("logs", [])
    logs.insert(0, {"ts": datetime.now().strftime("%H:%M:%S"), "level": level, "message": message})
    _session_set("logs", logs[:18])


def read_json(path: Path | None, default: Any = None) -> Any:
    if not path or not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def read_text(path: Path | None, default: str = "") -> str:
    if not path or not path.exists():
        return default
    return path.read_text(encoding="utf-8")


def current_path(session_key: str) -> Path | None:
    raw = _session_get(session_key)
    if not raw:
        return None
    path = Path(raw)
    return path if path.exists() else None


def save_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def domain_key(url: str) -> str:
    return safe_name(domain_from_url(url))


def build_audit_summary(path: Path) -> dict[str, Any]:
    data = read_json(path, {})
    return {
        "path": str(path),
        "name": path.name,
        "brand_name": data.get("brand_name") or domain_from_url(data.get("url", "example.com")),
        "url": data.get("url"),
        "geo_score": data.get("geo_score", 0),
        "date": data.get("date"),
        "scores": data.get("scores", {}),
        "findings": data.get("findings", []),
    }


def recent_audits(limit: int = 8) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in sorted(AUDITS_DIR.glob("*-audit-*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            items.append(build_audit_summary(path))
        except Exception:
            continue
        if len(items) >= limit:
            break
    return items


def artifact_entries(limit: int = 10) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for folder, kind in [(REPORTS_DIR, "report"), (PROPOSALS_DIR, "proposal"), (LLMS_DIR, "llms"), (AUDITS_DIR, "audit")]:
        for path in sorted(folder.glob("*"), key=lambda item: item.stat().st_mtime, reverse=True):
            if not path.is_file():
                continue
            entries.append({
                "path": str(path),
                "name": path.name,
                "kind": kind,
                "updated_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
    entries.sort(key=lambda item: item["updated_at"], reverse=True)
    return entries[:limit]


def compute_action_queue(audit: dict[str, Any] | None, current_prospect: dict[str, Any] | None, lang: str) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    if not audit:
        if lang == "zh":
            return [
                {"title": "先完成首次审计", "detail": "先输入一个域名，才能解锁报告、提案和对比功能。"},
                {"title": "先检查环境状态", "detail": "在客户演示前先跑环境诊断和登录检查，避免流程中断。"},
            ]
        return [
            {"title": "Run your first audit", "detail": "Start with a domain to unlock reports, proposals, and comparison views."},
            {"title": "Verify environment first", "detail": "Run doctor/auth checks before client demos to avoid avoidable failures."},
        ]

    findings = audit.get("findings", [])
    if findings:
        top = findings[0]
        actions.append(
            {
                "title": top.get("title", "优先处理最高风险问题" if lang == "zh" else "Prioritize highest-risk finding"),
                "detail": top.get("description", "建议先解决风险最高的阻断项。" if lang == "zh" else "Address the highest-risk blocker first."),
            }
        )

    if not current_prospect:
        actions.append(
            {
                "title": "将审计结果转为线索" if lang == "zh" else "Convert audit to prospect",
                "detail": "把分数、文件和备注绑定到线索记录，便于持续推进。" if lang == "zh" else "Attach scores, artifacts, and notes to a pipeline record.",
            }
        )
    else:
        actions.append(
            {
                "title": "生成客户提案" if lang == "zh" else "Prepare a client proposal",
                "detail": (
                    f"当前线索 {current_prospect.get('company')} 已可进入提案阶段。"
                    if lang == "zh"
                    else f"Prospect {current_prospect.get('company')} is ready for a proposal draft."
                ),
            }
        )

    if audit.get("scores", {}).get("llms", 0) < 50:
        actions.append(
            {
                "title": "补齐 llms.txt" if lang == "zh" else "Generate llms.txt",
                "detail": "建议先生成并审核 llms.txt，提升 AI 发现与引用效率。" if lang == "zh" else "Publish and review llms.txt to improve AI discoverability.",
            }
        )

    actions.append(
        {
            "title": "导出 PDF 报告" if lang == "zh" else "Export PDF report",
            "detail": "审计完成后立即导出 PDF，便于客户沟通和复盘归档。" if lang == "zh" else "Export a PDF right after audit completion for sharing and archive.",
        }
    )
    return actions[:4]


def find_recent_audit_for_domain(domain: str) -> Path | None:
    domain_safe = safe_name(domain)
    matches = sorted(AUDITS_DIR.glob(f"{domain_safe}-audit-*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def current_audit() -> dict[str, Any] | None:
    path = current_path("current_audit_path")
    if not path:
        return None
    return read_json(path, None)


def current_prospect() -> dict[str, Any] | None:
    pid = _session_get("current_prospect_id")
    if not pid:
        return None
    return find_prospect(load_prospects(), pid)


def report_preview(audit: dict[str, Any] | None) -> str:
    path = current_path("current_report_path")
    if path:
        return read_text(path)
    if audit:
        return render_report_md(audit)
    return ""


def proposal_preview(prospect: dict[str, Any] | None) -> str:
    path = current_path("current_proposal_path")
    if path:
        return read_text(path)
    if prospect:
        return generate_proposal_md(prospect, lang=current_lang())
    return ""


def compare_preview() -> str:
    path = current_path("current_compare_path")
    if not path:
        return ""
    return read_text(path)


def parse_compare_inputs() -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    baseline = current_path("compare_baseline_path")
    current = current_path("compare_current_path")
    return read_json(baseline, None), read_json(current, None)


def compare_score_changes(baseline: dict[str, Any] | None, current: dict[str, Any] | None, lang: str) -> list[dict[str, Any]]:
    if not baseline or not current:
        return []
    items = []
    baseline_scores = baseline.get("scores", {})
    current_scores = current.get("scores", {})
    for label_zh, label_en, key in [
        ("AI 可引用性", "AI Citability", "ai_citability"),
        ("品牌权威度", "Brand Authority", "brand_authority"),
        ("内容 E-E-A-T", "Content E-E-A-T", "content_eeat"),
        ("技术评分", "Technical", "technical"),
        ("结构化数据", "Schema", "schema"),
        ("平台优化", "Platform Optimization", "platform_optimization"),
    ]:
        before = int(baseline_scores.get(key, 0) or 0)
        after = int(current_scores.get(key, 0) or 0)
        items.append({"label": label_zh if lang == "zh" else label_en, "before": before, "after": after, "delta": after - before})
    return items


def compare_finding_diff(baseline: dict[str, Any] | None, current: dict[str, Any] | None) -> dict[str, list[str]]:
    if not baseline or not current:
        return {"resolved": [], "new": []}
    base_titles = {item.get("title") for item in baseline.get("findings", []) if item.get("title")}
    current_titles = {item.get("title") for item in current.get("findings", []) if item.get("title")}
    return {
        "resolved": sorted(base_titles - current_titles),
        "new": sorted(current_titles - base_titles),
    }


def env_snapshot() -> dict[str, Any]:
    status = detect_codex()
    return {
        "installed": status.installed,
        "logged_in": status.logged_in,
        "version": status.version,
        "message": status.message,
        "check_command": status.check_command,
        "ready": status.installed and status.logged_in,
        "audit_ready": True,
    }


def crm_stats(prospects: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(prospects)
    won = [item for item in prospects if item.get("status") == "won"]
    proposal = [item for item in prospects if item.get("status") == "proposal"]
    avg_score = round(sum(item.get("geo_score", 0) for item in prospects) / total) if total else 0
    pipeline = sum(int(item.get("monthly_value", 0) or 0) for item in proposal)
    won_value = sum(int(item.get("monthly_value", 0) or 0) for item in won)
    return {
        "total": total,
        "won": len(won),
        "proposal": len(proposal),
        "avg_score": avg_score,
        "pipeline": pipeline,
        "won_value": won_value,
    }


def download_href(path: str | None) -> str | None:
    if not path:
        return None
    resolved = Path(path)
    mapping = {
        AUDITS_DIR.resolve(): "audits",
        REPORTS_DIR.resolve(): "reports",
        PROPOSALS_DIR.resolve(): "proposals",
        LLMS_DIR.resolve(): "llms",
    }
    for root, kind in mapping.items():
        try:
            name = resolved.resolve().relative_to(root)
            return f"/downloads/{kind}/{name.as_posix()}"
        except Exception:
            continue
    return None


def build_context() -> dict[str, Any]:
    prospects = load_prospects()
    lang = current_lang()
    view_mode = _session_get("view_mode", "internal")
    active_tab = _session_get("active_tab", "workspace")
    current_audit_data = current_audit()
    current_prospect_data = current_prospect()
    recent = recent_audits()
    baseline, current = parse_compare_inputs()
    current_url = _session_get("current_url") or (current_audit_data or {}).get("url") or ""

    return {
        "tabs": [(key, labels[lang]) for key, labels in TAB_META],
        "active_tab": active_tab,
        "current_lang": lang,
        "view_mode": view_mode,
        "env": env_snapshot(),
        "current_url": current_url,
        "audit": current_audit_data,
        "report_preview": report_preview(current_audit_data),
        "proposal_preview": proposal_preview(current_prospect_data),
        "compare_preview": compare_preview(),
        "current_prospect": current_prospect_data,
        "prospects": prospects,
        "prospect_stats": crm_stats(prospects),
        "recent_runs": recent,
        "artifacts": artifact_entries(),
        "logs": _session_get("logs", []),
        "action_queue": compute_action_queue(current_audit_data, current_prospect_data, lang),
        "current_report_path": str(current_path("current_report_path") or ""),
        "current_pdf_path": str(current_path("current_pdf_path") or ""),
        "current_llms_path": str(current_path("current_llms_path") or ""),
        "current_llms_text": read_text(current_path("current_llms_path")),
        "compare_baseline_path": str(current_path("compare_baseline_path") or ""),
        "compare_current_path": str(current_path("compare_current_path") or ""),
        "compare_baseline": baseline,
        "compare_current": current,
        "compare_score_changes": compare_score_changes(baseline, current, lang),
        "compare_finding_diff": compare_finding_diff(baseline, current),
        "statuses": list(STATUS_META.keys()),
        "status_meta": STATUS_META,
    }


def render_shell():
    return render_template("_workspace_shell.html", **build_context())


# Routes

@app.route("/")
def index():
    return render_template("workspace.html", **build_context())


@app.post("/actions/tab")
def switch_tab():
    _session_set("active_tab", request.form.get("tab", "workspace"))
    pid = request.form.get("prospect_id")
    if pid:
        _session_set("current_prospect_id", pid)
    return render_shell()


@app.post("/actions/lang")
def switch_lang():
    lang = request.form.get("lang", "zh")
    _session_set("lang", lang if lang in LANGS else "zh")
    return render_shell()


@app.post("/actions/view-mode")
def switch_view_mode():
    mode = request.form.get("view_mode", "internal")
    _session_set("view_mode", mode if mode in {"internal", "client"} else "internal")
    add_log(
        f"{L('已切换到', 'Switched to')} {L('客户视图', 'client view') if mode == 'client' else L('内部视图', 'internal view')}."
    )
    return render_shell()


@app.post("/actions/doctor")
def run_doctor():
    env = env_snapshot()
    if env["ready"]:
        add_log(f"{L('环境就绪，Codex 已登录：', 'Environment ready, Codex logged in: ')}{env['version'] or L('已检测到', 'detected')}.", "success")
    elif env["installed"]:
        add_log(
            L(
                "已检测到 Codex CLI，但登录状态未确认。请先在终端执行 `codex login` 完成授权；Web 快速审计仍可继续。",
                "Codex CLI was detected, but login could not be confirmed. Run `codex login` in a terminal to authorize it; web audits can still continue.",
            ),
            "warning",
        )
    else:
        add_log(localize_env_message(env["message"]), "warning")
    return render_shell()


@app.post("/actions/auth")
def run_auth_check():
    env = env_snapshot()
    if env["logged_in"]:
        add_log(L("登录状态正常，可以发起新审计。", "Authentication confirmed. You can launch a fresh audit."), "success")
    else:
        add_log(
            L(
                "尚未确认 Codex 登录状态。请在终端执行 `codex login`，完成后回到这里点一次“检查登录”。Web 快速审计也可以先继续。",
                "Codex login is not confirmed. Run `codex login` in a terminal, then come back and click Check Auth. Web audits can also continue first.",
            ),
            "warning",
        )
    return render_shell()


@app.post("/actions/audit")
def launch_audit():
    url = request.form.get("url", "").strip()
    try:
        url = ensure_url(url)
    except Exception as exc:
        add_log(f"{L('输入网址无效：', 'Invalid URL: ')}{exc}", "danger")
        _session_set("active_tab", "workspace")
        return render_shell()

    env = env_snapshot()
    if not env["logged_in"]:
        add_log(
            L(
                "未确认 Codex 登录状态，已继续执行本地快速审计。",
                "Codex login is not confirmed; continuing with the local web audit.",
            ),
            "warning",
        )

    audit = run_audit(url)
    files = save_audit_artifacts(audit, AUDITS_DIR)
    report_path = REPORTS_DIR / f"{domain_key(url)}-geo-client-report-{audit['date']}.md"
    save_text(report_path, render_report_md(audit))

    _session_set("current_url", url)
    _session_set("current_audit_path", str(files["audit_json"]))
    _session_set("current_report_path", str(report_path))
    _session_set("active_tab", "audit")
    add_log(
        f"{L('审计完成：', 'Audit finished: ')}{domain_from_url(url)}，{L('GEO 分数', 'GEO score')} {audit['geo_score']}/100。",
        "success",
    )
    return render_shell()


@app.post("/actions/select-run")
def select_run():
    path = request.form.get("path", "")
    audit_path = Path(path)
    if not audit_path.exists():
        add_log(L("未找到所选审计文件。", "Selected audit file was not found."), "danger")
        return render_shell()
    audit = read_json(audit_path, {})
    _session_set("current_audit_path", str(audit_path))
    _session_set("current_url", audit.get("url", ""))
    _session_set("active_tab", request.form.get("tab", "audit"))
    add_log(f"{L('已加载历史审计：', 'Loaded saved audit: ')}{audit.get('brand_name') or audit.get('url')}。")
    return render_shell()


@app.post("/actions/report")
def generate_report_action():
    audit = current_audit()
    if not audit:
        add_log(L("尚未选择审计结果。请先执行或加载一次审计。", "No audit selected. Run or load an audit first."), "danger")
        return render_shell()
    path = REPORTS_DIR / f"{domain_key(audit['url'])}-geo-client-report-{audit['date']}.md"
    save_text(path, render_report_md(audit))
    _session_set("current_report_path", str(path))
    _session_set("active_tab", "reports")
    add_log(f"{L('Markdown 报告已生成：', 'Markdown report generated: ')}{path.name}", "success")
    return render_shell()


@app.post("/actions/pdf")
def generate_pdf_action():
    audit_path = current_path("current_audit_path")
    audit = current_audit()
    if not audit_path or not audit:
        add_log(L("没有可用于导出 PDF 的审计结果。", "No audit available for PDF export."), "danger")
        return render_shell()
    output = REPORTS_DIR / f"{domain_key(audit['url'])}-geo-report-{audit['date']}.pdf"
    run_pdf(str(audit_path), str(output))
    _session_set("current_pdf_path", str(output))
    _session_set("active_tab", "reports")
    add_log(f"{L('PDF 已导出：', 'PDF exported: ')}{output.name}", "success")
    return render_shell()


@app.post("/actions/llms")
def generate_llms_action():
    audit = current_audit()
    current_url = _session_get("current_url")
    url = current_url or (audit or {}).get("url")
    if not url:
        add_log(L("未找到当前 URL，无法生成 llms.txt。", "No active URL found for llms.txt generation."), "danger")
        return render_shell()
    full = request.form.get("full") == "on"
    data = generate_llms(url, full=full)
    suffix = "llms-full" if full else "llms"
    path = LLMS_DIR / f"{domain_key(url)}-{suffix}-{now_date()}.txt"
    save_text(path, data["content"])
    _session_set("current_llms_path", str(path))
    _session_set("active_tab", "reports")
    add_log(
        (
            f"{L('已生成', 'Generated ')}{L('完整 ', 'full ') if full else ''}llms.txt "
            f"{L('草稿：', 'draft for ')}{domain_from_url(url)}。"
        ),
        "success",
    )
    return render_shell()


@app.post("/actions/add-prospect")
def add_prospect_action():
    audit = current_audit()
    if not audit:
        add_log(L("尚未选择审计结果。请先完成审计再加入线索。", "No audit selected. Add a prospect after an audit finishes."), "danger")
        return render_shell()

    prospects = load_prospects()
    domain = domain_from_url(audit["url"])
    existing = find_prospect(prospects, domain)
    monthly_value = int(request.form.get("monthly_value", 0) or 0)
    report_path = current_path("current_report_path")

    if existing:
        existing["geo_score"] = audit.get("geo_score", 0)
        existing["audit_date"] = audit.get("date")
        existing["audit_file"] = str(report_path) if report_path else existing.get("audit_file")
        existing["updated_at"] = now_date()
        if monthly_value:
            existing["monthly_value"] = monthly_value
        prospect = existing
        add_log(f"{L('已更新已有线索：', 'Updated existing prospect ')}{existing['id']}。", "success")
    else:
        pid = f"PRO-{len(prospects) + 1:03d}"
        prospect = {
            "id": pid,
            "company": audit.get("brand_name") or domain.split(".")[0].title(),
            "domain": domain,
            "status": "lead",
            "geo_score": audit.get("geo_score", 0),
            "audit_date": audit.get("date"),
            "audit_file": str(report_path) if report_path else "",
            "proposal_file": "",
            "monthly_value": monthly_value,
            "notes": [],
            "created_at": now_date(),
            "updated_at": now_date(),
        }
        prospects.append(prospect)
        add_log(f"{L('已创建新线索：', 'Created new prospect ')}{pid} ({domain})。", "success")

    save_prospects(prospects)
    _session_set("current_prospect_id", prospect["id"])
    _session_set("active_tab", "prospects")
    return render_shell()


@app.post("/actions/select-prospect")
def select_prospect():
    pid = request.form.get("prospect_id", "")
    prospect = find_prospect(load_prospects(), pid)
    if not prospect:
        add_log(L("未找到所选线索。", "Selected prospect was not found."), "danger")
        return render_shell()

    _session_set("current_prospect_id", pid)
    tab = request.form.get("tab", "prospects")
    _session_set("active_tab", tab)

    audit_path = find_recent_audit_for_domain(prospect["domain"])
    if audit_path:
        _session_set("current_audit_path", str(audit_path))
        _session_set("current_url", f"https://{prospect['domain']}")

    add_log(f"{L('已打开线索：', 'Opened prospect ')}{prospect['company']}。")
    return render_shell()


@app.post("/actions/prospect/status")
def update_prospect_status():
    pid = request.form.get("prospect_id", "")
    status = request.form.get("status", "")
    prospects = load_prospects()
    prospect = find_prospect(prospects, pid)
    if not prospect or status not in STATUS_META:
        add_log(L("无法更新线索状态。", "Unable to update prospect status."), "danger")
        return render_shell()
    prospect["status"] = status
    prospect["updated_at"] = now_date()
    save_prospects(prospects)
    _session_set("current_prospect_id", pid)
    _session_set("active_tab", "prospects")
    label = STATUS_META[status]["label"][current_lang()]
    add_log(f"{L('线索', 'Prospect ')} {prospect['company']} {L('状态已更新为', 'moved to')} {label}。", "success")
    return render_shell()


@app.post("/actions/prospect/value")
def update_prospect_value():
    pid = request.form.get("prospect_id", "")
    monthly_value = int(request.form.get("monthly_value", 0) or 0)
    prospects = load_prospects()
    prospect = find_prospect(prospects, pid)
    if not prospect:
        add_log(L("无法更新月度价值。", "Unable to update monthly value."), "danger")
        return render_shell()
    prospect["monthly_value"] = monthly_value
    prospect["updated_at"] = now_date()
    save_prospects(prospects)
    _session_set("current_prospect_id", pid)
    add_log(f"{L('月度价值已更新：', 'Monthly value updated for ')}{prospect['company']}。", "success")
    return render_shell()


@app.post("/actions/prospect/note")
def add_prospect_note():
    pid = request.form.get("prospect_id", "")
    text = request.form.get("text", "").strip()
    prospects = load_prospects()
    prospect = find_prospect(prospects, pid)
    if not prospect or not text:
        add_log(L("无法保存备注。", "Unable to save note."), "danger")
        return render_shell()
    notes = prospect.setdefault("notes", [])
    notes.append({"date": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), "text": text})
    prospect["updated_at"] = now_date()
    save_prospects(prospects)
    _session_set("current_prospect_id", pid)
    add_log(f"{L('已添加备注到：', 'Added note to ')}{prospect['company']}。", "success")
    return render_shell()


@app.post("/actions/proposal")
def generate_proposal_action():
    pid = request.form.get("prospect_id") or _session_get("current_prospect_id")
    prospects = load_prospects()
    prospect = find_prospect(prospects, pid) if pid else None

    if not prospect:
        audit = current_audit()
        if not audit:
            add_log(L("没有可用线索或审计结果，无法生成提案。", "No prospect or audit selected for proposal generation."), "danger")
            return render_shell()
        domain = domain_from_url(audit["url"])
        prospect = {
            "id": "AD-HOC",
            "company": audit.get("brand_name") or domain.split(".")[0].title(),
            "domain": domain,
            "geo_score": audit.get("geo_score", 0),
            "monthly_value": int(request.form.get("monthly_value", 5000) or 5000),
        }
    else:
        monthly_value = int(request.form.get("monthly_value", prospect.get("monthly_value", 0)) or 0)
        prospect["monthly_value"] = monthly_value or prospect.get("monthly_value", 0) or 5000
        prospect["updated_at"] = now_date()
        save_prospects(prospects)

    content = generate_proposal_md(prospect, lang=current_lang())
    path = PROPOSALS_DIR / f"{safe_name(prospect['domain'])}-proposal-{now_date()}.md"
    save_text(path, content)
    _session_set("current_proposal_path", str(path))
    _session_set("active_tab", "proposal")
    if prospect.get("id") and prospect.get("id") != "AD-HOC":
        stored = find_prospect(prospects, prospect["id"])
        if stored:
            stored["proposal_file"] = str(path)
            stored["updated_at"] = now_date()
            save_prospects(prospects)
            _session_set("current_prospect_id", stored["id"])
    add_log(f"{L('提案草稿已生成：', 'Proposal draft generated for ')}{prospect['company']}。", "success")
    return render_shell()


@app.post("/actions/compare")
def generate_compare_action():
    baseline_path = Path(request.form.get("baseline_path", ""))
    current_path_value = Path(request.form.get("current_path", ""))
    if not baseline_path.exists() or not current_path_value.exists():
        add_log(L("请先选择两份有效审计快照再执行对比。", "Select two valid audit snapshots before comparing."), "danger")
        return render_shell()

    baseline = read_json(baseline_path, {})
    current = read_json(current_path_value, {})
    company = current.get("brand_name") or domain_from_url(current.get("url", "example.com"))
    text = generate_compare_md(baseline, current, company)
    out = REPORTS_DIR / f"{safe_name(company)}-monthly-{now_date()}.md"
    save_text(out, text)

    _session_set("compare_baseline_path", str(baseline_path))
    _session_set("compare_current_path", str(current_path_value))
    _session_set("current_compare_path", str(out))
    _session_set("active_tab", "compare")
    add_log(f"{L('对比报告已生成：', 'Comparison report generated for ')}{company}。", "success")
    return render_shell()


@app.route("/downloads/<kind>/<path:name>")
def download(kind: str, name: str):
    mapping = {
        "audits": AUDITS_DIR,
        "reports": REPORTS_DIR,
        "proposals": PROPOSALS_DIR,
        "llms": LLMS_DIR,
    }
    root = mapping.get(kind)
    if not root:
        abort(404)
    path = (root / name).resolve()
    if not str(path).startswith(str(root.resolve())) or not path.exists():
        abort(404)
    return send_file(path, as_attachment=True, download_name=path.name)


if __name__ == "__main__":
    app.run(debug=True, port=5050)

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .auth import detect_codex
from .utils import domain_from_url, ensure_url, now_date, safe_name


def _print_json(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_doctor(args):
    status = detect_codex()
    payload = {
        "codex_installed": status.installed,
        "codex_logged_in": status.logged_in,
        "codex_version": status.version,
        "check_command": status.check_command,
        "message": status.message,
        "next_step": None if status.logged_in else "Run: codex login",
    }
    if args.json:
        _print_json(payload)
        return 0

    print("GEO Doctor")
    print(f"- Codex CLI installed: {'yes' if status.installed else 'no'}")
    if status.version:
        print(f"- Codex version: {status.version}")
    print(f"- Logged in: {'yes' if status.logged_in else 'no'}")
    print(f"- Status: {status.message}")
    if not status.logged_in:
        print("- Next: codex login")
    return 0 if status.installed else 2


def cmd_auth(args):
    status = detect_codex()
    out = {
        "installed": status.installed,
        "logged_in": status.logged_in,
        "message": status.message,
        "hint": "Use official login flow: codex login",
    }
    if args.json:
        _print_json(out)
    else:
        print("Codex auth status")
        print(f"- installed: {status.installed}")
        print(f"- logged_in: {status.logged_in}")
        print(f"- message: {status.message}")
        if not status.logged_in:
            print("- command: codex login")
    return 0


def cmd_audit(args):
    from .services import run_audit, save_audit_artifacts

    audit = run_audit(args.url)
    files = save_audit_artifacts(audit, Path(args.output_dir) if args.output_dir else None)
    if args.json:
        _print_json({"audit": audit, "files": {k: str(v) for k, v in files.items()}})
    else:
        print(f"GEO score: {audit['geo_score']}/100")
        print(f"Audit JSON: {files['audit_json']}")
        print(f"Report MD: {files['report_md']}")
    return 0


def cmd_quick(args):
    from .services import run_audit

    audit = run_audit(args.url)
    out = {
        "url": audit["url"],
        "brand_name": audit["brand_name"],
        "geo_score": audit["geo_score"],
        "scores": audit["scores"],
        "platforms": audit["platforms"],
    }
    if args.json:
        _print_json(out)
    else:
        print(f"{out['brand_name']}: GEO {out['geo_score']}/100")
        print(f"AI Citability: {out['scores']['ai_citability']}/100")
        print(f"Technical: {out['scores']['technical']}/100")
    return 0


def cmd_citability(args):
    from scripts.citability_scorer import analyze_page_citability

    data = analyze_page_citability(ensure_url(args.url))
    if args.json:
        _print_json(data)
    else:
        print(f"Average citability: {data.get('average_citability_score', 0)}/100")
        print(f"Blocks analyzed: {data.get('total_blocks_analyzed', 0)}")
    return 0


def cmd_crawlers(args):
    from scripts.fetch_page import fetch_robots_txt

    data = fetch_robots_txt(ensure_url(args.url))
    if args.json:
        _print_json(data)
    else:
        print(f"robots.txt: {'found' if data.get('exists') else 'missing'}")
        print(f"AI crawlers tracked: {len(data.get('ai_crawler_status', {}))}")
    return 0


def cmd_llmstxt(args):
    from .services import generate_llms

    if args.mode == "analyze":
        from scripts.llmstxt_generator import validate_llmstxt

        data = validate_llmstxt(ensure_url(args.url))
        if args.json:
            _print_json(data)
        else:
            print(f"llms.txt exists: {data.get('exists')}")
            print(f"format valid: {data.get('format_valid')}")
    else:
        data = generate_llms(args.url, full=args.full)
        if args.output:
            Path(args.output).write_text(data["content"], encoding="utf-8")
            print(f"Wrote {args.output}")
        elif args.json:
            _print_json(data)
        else:
            print(data["content"])
    return 0


def cmd_brands(args):
    from scripts.brand_scanner import generate_brand_report

    report = generate_brand_report(args.brand_name, args.domain)
    if args.json:
        _print_json(report)
    else:
        print(f"Brand report generated for: {args.brand_name}")
        print("Platforms:", ", ".join(report.get("platforms", {}).keys()))
    return 0


def cmd_platforms(args):
    from .services import run_audit

    audit = run_audit(args.url)
    out = {"url": audit["url"], "platforms": audit["platforms"]}
    if args.json:
        _print_json(out)
    else:
        for k, v in out["platforms"].items():
            print(f"{k}: {v}/100")
    return 0


def cmd_schema(args):
    from scripts.fetch_page import fetch_page

    page = fetch_page(ensure_url(args.url))
    schemas = page.get("structured_data", [])
    out = {"url": args.url, "count": len(schemas), "schemas": schemas}
    if args.json:
        _print_json(out)
    else:
        print(f"Detected schema blocks: {len(schemas)}")
    return 0


def cmd_technical(args):
    from .services import run_audit

    audit = run_audit(args.url)
    out = {
        "url": audit["url"],
        "technical": audit["scores"]["technical"],
        "findings": [f for f in audit.get("findings", []) if f.get("severity") in {"critical", "high"}],
    }
    if args.json:
        _print_json(out)
    else:
        print(f"Technical score: {out['technical']}/100")
        for f in out["findings"]:
            print(f"- [{f['severity'].upper()}] {f['title']}")
    return 0


def cmd_content(args):
    from .services import run_audit

    audit = run_audit(args.url)
    out = {
        "url": audit["url"],
        "content_eeat": audit["scores"]["content_eeat"],
        "citability": audit["scores"]["ai_citability"],
    }
    if args.json:
        _print_json(out)
    else:
        print(f"Content/E-E-A-T score: {out['content_eeat']}/100")
        print(f"Citability: {out['citability']}/100")
    return 0


def cmd_report(args):
    from .services import run_audit, save_audit_artifacts

    audit = run_audit(args.url)
    files = save_audit_artifacts(audit, Path(args.output_dir) if args.output_dir else None)
    if args.json:
        _print_json({"report": str(files["report_md"]), "audit_json": str(files["audit_json"])})
    else:
        print(f"Generated report: {files['report_md']}")
    return 0


def cmd_report_pdf(args):
    from .services import run_pdf

    out = run_pdf(args.input, args.output)
    if args.json:
        _print_json({"pdf": out})
    else:
        print(f"Generated PDF: {out}")
    return 0


def cmd_prospect(args):
    from .services import find_prospect, load_prospects, run_audit, save_audit_artifacts, save_prospects

    items = load_prospects()

    if args.prospect_cmd == "new":
        domain = domain_from_url(args.domain)
        pid = f"PRO-{len(items)+1:03d}"
        company = domain.split(".")[0].replace("-", " ").title()
        rec = {
            "id": pid,
            "company": company,
            "domain": domain,
            "status": "lead",
            "geo_score": 0,
            "audit_date": None,
            "audit_file": None,
            "proposal_file": None,
            "monthly_value": args.monthly_value or 0,
            "notes": [],
            "created_at": now_date(),
            "updated_at": now_date(),
        }
        items.append(rec)
        save_prospects(items)
        print(f"Created prospect {pid} for {domain}")
        return 0

    if args.prospect_cmd == "list":
        out = items
        if args.status:
            out = [i for i in items if i.get("status") == args.status]
        if args.json:
            _print_json(out)
        else:
            for it in out:
                print(f"{it['id']} {it['domain']} {it.get('status')} {it.get('geo_score', 0)}/100")
        return 0

    if args.prospect_cmd == "show":
        p = find_prospect(items, args.key)
        if not p:
            print("Prospect not found", file=sys.stderr)
            return 1
        if args.json:
            _print_json(p)
        else:
            print(json.dumps(p, indent=2, ensure_ascii=False))
        return 0

    if args.prospect_cmd == "audit":
        p = find_prospect(items, args.key)
        if not p:
            print("Prospect not found", file=sys.stderr)
            return 1
        audit = run_audit(p["domain"])
        p["geo_score"] = audit["geo_score"]
        p["audit_date"] = now_date()
        files = save_audit_artifacts(audit, Path.home() / ".geo-prospects" / "audits")
        p["audit_file"] = str(files["report_md"])
        p["updated_at"] = now_date()
        save_prospects(items)
        print(f"Updated {p['id']} score={p['geo_score']}")
        return 0

    if args.prospect_cmd == "note":
        p = find_prospect(items, args.key)
        if not p:
            print("Prospect not found", file=sys.stderr)
            return 1
        p.setdefault("notes", []).append({"date": now_date(), "text": args.text})
        p["updated_at"] = now_date()
        save_prospects(items)
        print("Note added")
        return 0

    if args.prospect_cmd == "status":
        p = find_prospect(items, args.key)
        if not p:
            print("Prospect not found", file=sys.stderr)
            return 1
        p["status"] = args.status
        p["updated_at"] = now_date()
        save_prospects(items)
        print(f"Status updated: {p['status']}")
        return 0

    print("Unknown prospect command", file=sys.stderr)
    return 2


def cmd_proposal(args):
    from .services import find_prospect, generate_proposal_md, load_prospects

    items = load_prospects()
    p = find_prospect(items, args.key)
    if not p:
        p = {
            "company": domain_from_url(args.key).split(".")[0].title(),
            "domain": domain_from_url(args.key),
            "geo_score": 0,
            "monthly_value": args.monthly_value or 5000,
        }
    text = generate_proposal_md(p)
    out_dir = Path.home() / ".geo-prospects" / "proposals"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{safe_name(p['domain'])}-proposal-{now_date()}.md"
    path.write_text(text, encoding="utf-8")
    print(f"Generated proposal: {path}")
    return 0


def cmd_compare(args):
    from .services import generate_compare_md

    p1 = Path(args.baseline)
    p2 = Path(args.current)
    b = json.loads(p1.read_text(encoding="utf-8"))
    c = json.loads(p2.read_text(encoding="utf-8"))
    company = c.get("brand_name") or domain_from_url(c.get("url", "example.com"))
    text = generate_compare_md(b, c, company)
    out_dir = Path.home() / ".geo-prospects" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{safe_name(company)}-monthly-{now_date()}.md"
    out.write_text(text, encoding="utf-8")
    print(f"Generated compare report: {out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="geo", description="GEO dual-stack CLI (Codex + Claude)")
    p.add_argument("--version", action="version", version=f"geo {__version__}")

    sp = p.add_subparsers(dest="cmd", required=True)

    # infra
    auth = sp.add_parser("auth", help="Check Codex auth state")
    auth.add_argument("--json", action="store_true")
    auth.set_defaults(func=cmd_auth)

    doctor = sp.add_parser("doctor", help="Environment diagnostics")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    # analysis
    for name, fn in [
        ("audit", cmd_audit),
        ("quick", cmd_quick),
        ("citability", cmd_citability),
        ("crawlers", cmd_crawlers),
        ("platforms", cmd_platforms),
        ("schema", cmd_schema),
        ("technical", cmd_technical),
        ("content", cmd_content),
        ("report", cmd_report),
    ]:
        c = sp.add_parser(name)
        c.add_argument("url")
        c.add_argument("--json", action="store_true")
        if name in {"audit", "report"}:
            c.add_argument("--output-dir")
        c.set_defaults(func=fn)

    llms = sp.add_parser("llmstxt")
    llms.add_argument("url")
    llms.add_argument("--mode", choices=["analyze", "generate"], default="analyze")
    llms.add_argument("--full", action="store_true")
    llms.add_argument("--output")
    llms.add_argument("--json", action="store_true")
    llms.set_defaults(func=cmd_llmstxt)

    brands = sp.add_parser("brands")
    brands.add_argument("brand_name")
    brands.add_argument("--domain")
    brands.add_argument("--json", action="store_true")
    brands.set_defaults(func=cmd_brands)

    pdf = sp.add_parser("report-pdf")
    pdf.add_argument("input", help="Audit JSON file path or URL")
    pdf.add_argument("--output", default="GEO-REPORT.pdf")
    pdf.add_argument("--json", action="store_true")
    pdf.set_defaults(func=cmd_report_pdf)

    # CRM
    prospect = sp.add_parser("prospect")
    psp = prospect.add_subparsers(dest="prospect_cmd", required=True)

    pn = psp.add_parser("new")
    pn.add_argument("domain")
    pn.add_argument("--monthly-value", type=int)

    pl = psp.add_parser("list")
    pl.add_argument("--status")
    pl.add_argument("--json", action="store_true")

    pshow = psp.add_parser("show")
    pshow.add_argument("key")
    pshow.add_argument("--json", action="store_true")

    pa = psp.add_parser("audit")
    pa.add_argument("key")

    pnote = psp.add_parser("note")
    pnote.add_argument("key")
    pnote.add_argument("text")

    ps = psp.add_parser("status")
    ps.add_argument("key")
    ps.add_argument("status")

    prospect.set_defaults(func=cmd_prospect)

    proposal = sp.add_parser("proposal")
    proposal.add_argument("key", help="Prospect id/domain")
    proposal.add_argument("--monthly-value", type=int)
    proposal.set_defaults(func=cmd_proposal)

    compare = sp.add_parser("compare")
    compare.add_argument("baseline", help="Baseline audit JSON path")
    compare.add_argument("current", help="Current audit JSON path")
    compare.set_defaults(func=cmd_compare)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

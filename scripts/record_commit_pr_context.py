#!/usr/bin/env python3
"""
record_commit_pr_context.py

Generates a markdown documentation summary of a git commit and saves it
to markdowns/PR_context/ for tracking PR context, architecture alignment,
and team coordination.
"""

import argparse
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path


def run_git(args: list[str], cwd: Path) -> str:
    """Run a git command and return its trimmed stdout."""
    res = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if res.returncode != 0:
        raise RuntimeError(f"Git command failed: git {' '.join(args)}\nError: {res.stderr}")
    return res.stdout.strip()


def slugify(text: str) -> str:
    """Convert commit subject into a filesystem-safe slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:40].strip("_") or "commit"


def get_commit_details(commit_ref: str, repo_root: Path) -> dict:
    """Extract full metadata and diff statistics for a commit."""
    # Commit SHA and info
    full_sha = run_git(["rev-parse", commit_ref], repo_root)
    short_sha = run_git(["rev-parse", "--short", commit_ref], repo_root)
    author_name = run_git(["log", "-1", "--format=%an", full_sha], repo_root)
    author_email = run_git(["log", "-1", "--format=%ae", full_sha], repo_root)
    date_iso = run_git(["log", "-1", "--format=%cI", full_sha], repo_root)
    subject = run_git(["log", "-1", "--format=%s", full_sha], repo_root)
    body = run_git(["log", "-1", "--format=%b", full_sha], repo_root).strip()

    # Current branch (or detached HEAD)
    try:
        branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], repo_root)
    except Exception:
        branch = "unknown"

    # Stat and file status
    # Parent count to handle root commit vs normal commit
    parents = run_git(["log", "-1", "--format=%P", full_sha], repo_root).split()
    if not parents:
        # Initial root commit: diff with empty tree
        empty_tree = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        name_status = run_git(["diff-tree", "--no-commit-id", "--name-status", "-r", empty_tree, full_sha], repo_root)
        diff_stat = run_git(["diff-tree", "--no-commit-id", "--stat", "-r", empty_tree, full_sha], repo_root)
    else:
        name_status = run_git(["diff-tree", "--no-commit-id", "--name-status", "-r", full_sha], repo_root)
        diff_stat = run_git(["show", "--stat", "--format=", full_sha], repo_root)

    return {
        "full_sha": full_sha,
        "short_sha": short_sha,
        "author": f"{author_name} <{author_email}>",
        "date_iso": date_iso,
        "subject": subject,
        "body": body,
        "branch": branch,
        "name_status": name_status,
        "diff_stat": diff_stat,
    }


def categorize_components(file_list_raw: str) -> list[str]:
    """Map changed files to architectural components based on PRISM_RAG architecture."""
    lines = [line.strip() for line in file_list_raw.splitlines() if line.strip()]
    files = [line.split(maxsplit=1)[-1] for line in lines]

    components = set()
    for f in files:
        f_lower = f.lower()
        if "controller" in f_lower:
            components.add("Component 1: Retrieval Controller (Cascade / Speculation)")
        elif "decompos" in f_lower:
            components.add("Component 2: Intent Decomposition")
        elif "retriev" in f_lower or "fusion" in f_lower or "rerank" in f_lower or "index" in f_lower:
            components.add("Component 3: Corpus Retrieval & Fusion")
        elif "refine" in f_lower or "ground" in f_lower or "claim" in f_lower or "delta" in f_lower or "uncertainty" in f_lower:
            components.add("Component 4: Session Refinement & Corpus Grounding")
        elif "telemetry" in f_lower or "harness" in f_lower or "replay" in f_lower or "grafana" in f_lower or "events" in f_lower:
            components.add("Component 5: Telemetry & Integration Harness")
        elif "schema" in f_lower:
            components.add("Core Schemas & Contract (FROZEN)")
        elif f_lower.startswith("markdowns/"):
            components.add("Documentation / Markdowns")
        elif f_lower.startswith("tests/") or "test" in f_lower:
            components.add("Tests & Verification")
        else:
            components.add("General / Infrastructure")

    return sorted(components) if components else ["General / Core"]


def build_markdown_content(details: dict) -> str:
    """Format commit details into structured PR Context markdown."""
    components = categorize_components(details["name_status"])
    components_md = "\n".join(f"- {c}" for c in components)

    # Format file status
    file_lines = []
    for line in details["name_status"].splitlines():
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        status_code = parts[0]
        file_path = parts[1] if len(parts) > 1 else ""
        status_map = {
            "A": "Added",
            "M": "Modified",
            "D": "Deleted",
            "R": "Renamed",
            "C": "Copied",
        }
        status_label = status_map.get(status_code[0], status_code)
        file_lines.append(f"- **{status_label}**: `{file_path}`")
    files_md = "\n".join(file_lines) if file_lines else "- No files listed"

    # Check for contract impact
    has_schema_change = any("schema" in line.lower() for line in details["name_status"].splitlines())
    schema_alert = ""
    if has_schema_change:
        schema_alert = (
            "> [!WARNING]\n"
            "> **Interface Contract Impact**: This commit modifies schemas or contract files. "
            "Please ensure team alignment across all 4 module owners per `C_TEAM_COORDINATION.md`.\n\n"
        )

    body_section = details["body"] if details["body"] else "*No extended description provided in commit message.*"

    content = f"""# Commit Context: {details['short_sha']} — {details['subject']}

{schema_alert}## Metadata
- **Commit SHA**: `{details['full_sha']}` (`{details['short_sha']}`)
- **Author**: {details['author']}
- **Date**: `{details['date_iso']}`
- **Branch**: `{details['branch']}`

## Commit Message
```text
{details['subject']}

{details['body']}
```

## Architectural Components Impacted
{components_md}

## File Changes
{files_md}

## Diff Statistics
```text
{details['diff_stat']}
```

## Description & Context
{body_section}

## PR Integration & Alignment Checklist
- [ ] Conforms to frozen Pydantic schemas (`core/schemas.py`)
- [ ] Golden replay test (`slrag replay --stream golden_example.jsonl`) verified (if applicable)
- [ ] Unit tests / verification executed
- [ ] No contract drift introduced across component boundaries
"""
    return content.strip() + "\n"


def main():
    parser = argparse.ArgumentParser(description="Generate PR context markdown for a git commit.")
    parser.add_argument(
        "--commit",
        default="HEAD",
        help="Commit reference to document (default: HEAD)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Target directory (default: markdowns/PR_context)",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    output_dir = Path(args.output_dir) if args.output_dir else repo_root / "markdowns" / "PR_context"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        details = get_commit_details(args.commit, repo_root)
    except Exception as e:
        print(f"Error reading commit details: {e}", file=sys.stderr)
        sys.exit(1)

    # Clean timestamp for filename: YYYYMMDD_HHMMSS
    try:
        dt = datetime.datetime.fromisoformat(details["date_iso"])
        ts_str = dt.strftime("%Y%m%d_%H%M%S")
    except Exception:
        ts_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    slug = slugify(details["subject"])
    filename = f"{ts_str}_{details['short_sha']}_{slug}.md"
    target_path = output_dir / filename

    content = build_markdown_content(details)
    target_path.write_text(content, encoding="utf-8")

    print(f"Successfully generated PR context markdown:\n{target_path}")


if __name__ == "__main__":
    main()

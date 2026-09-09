"""Read-only environment check; never contacts providers or runs the test gate."""
import json
from pathlib import Path
import shutil
import sys


def main():
    root = Path(__file__).resolve().parents[1]
    skills = ["voc-workflow", "voc-slice", "orca-cli", "orchestration"]
    required_entries = [
        "README.md",
        "AGENTS.md",
        "docs/INDEX.md",
        "docs/PROJECT_OVERVIEW.md",
        "docs/ARCHITECTURE.md",
        "nexus/__main__.py",
        "tests/test_nexus.py",
        "fixtures/event.json",
        "fixtures/corpus.json",
    ]
    checks = {
        "python_3_9_plus": sys.version_info >= (3, 9),
        "claude_points_to_agents": (root / "CLAUDE.md").is_symlink()
        and (root / "CLAUDE.md").resolve() == root / "AGENTS.md",
        "skills": all((root / ".agents/skills" / skill / "SKILL.md").is_file() for skill in skills),
        "skill_links": all((root / runtime / "skills").is_symlink()
                           and (root / runtime / "skills").resolve() == root / ".agents/skills"
                           for runtime in (".claude", ".opencode", ".omp")),
        "required_repo_entries": all((root / path).is_file() for path in required_entries),
    }
    print(json.dumps({
        "purpose": "environment",
        "checks": checks,
        "optional_binaries": {name: shutil.which(name) is not None
                               for name in ("orca", "opencode", "omp")},
        "provider_auth_checked": False,
        "runtime_gate": "not_run",
        "tests_run": False,
    }, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

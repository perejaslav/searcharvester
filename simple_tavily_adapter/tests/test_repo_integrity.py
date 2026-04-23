"""Repository-level regression checks for deployment/docs drift."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_docker_compose_has_no_masked_env_placeholders():
    text = (ROOT / "docker-compose.yaml").read_text()
    for phrase in ("OPEN...Y", "ANTH...Y", "GEMI...Y", "GOOG...Y", "OLLA...Y"):
        assert phrase not in text


def test_readme_no_removed_research_architecture_claims():
    readme = (ROOT / "README.md").read_text().lower()
    forbidden = [
        "docker-socket-proxy",
        "docker http api",
        "ephemeral, one per /research",
        "watches for the `report_saved:` marker",
        "/workspace/report.md",
    ]
    for phrase in forbidden:
        assert phrase not in readme


def test_readme_mentions_current_acp_flow():
    readme = (ROOT / "README.md").read_text().lower()
    for phrase in ("hermes acp", "session_update", "events", "./report.md"):
        assert phrase in readme

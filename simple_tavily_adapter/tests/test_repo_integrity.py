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


def test_lite_compose_exists_and_disables_research():
    text = (ROOT / "docker-compose.lite.yaml").read_text()
    assert "Dockerfile.lite" in text
    assert "RESEARCH_DISABLED=1" in text
    assert "searcharvester-lite-adapter" in text
    assert "frontend" not in text
    assert "nousresearch/hermes-agent" not in text


def test_lite_dockerfile_is_not_based_on_hermes_image():
    text = (ROOT / "simple_tavily_adapter" / "Dockerfile.lite").read_text()
    assert "FROM python:3.11-slim" in text
    assert "nousresearch/hermes-agent" not in text
    assert "RESEARCH_DISABLED=1" in text

"""Tests for deep_think_pipeline.py: Pipeline-level static regression guards."""

from pathlib import Path


def test_pipe_uses_utc_for_date():
    """Regression guard: pipe() must compute today in UTC."""
    dtp_path = (
        Path(__file__).resolve().parent.parent
        / "pipelines/workflows/deep_think_pipeline.py"
    )
    source = dtp_path.read_text()
    assert "datetime.timezone.utc" in source, (
        "pipe() must use datetime.datetime.now(datetime.timezone.utc), "
        "not datetime.date.today()"
    )

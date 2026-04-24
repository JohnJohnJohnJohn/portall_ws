from pathlib import Path


def test_conventions_md_exists():
    path = Path(__file__).parent.parent / "CONVENTIONS.md"
    assert path.exists()

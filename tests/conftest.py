"""Shared fixtures. pytest auto-discovers this file; no import needed in the tests."""
from pathlib import Path

import pytest

from pipeline.schema import Line

FIXTURES = Path(__file__).parent / "fixtures"


class SampleDir:
    """The folder of sample newspaper PDFs. `sample_dir / "name.pdf"` gives the path, or SKIPS the test.

    The PDFs are real newspaper pages (copyrighted), so they are not stored in the git repository.
    On a machine that does not have them (GitHub Actions, a fresh clone) the tests that need them
    are skipped with a clear reason instead of failing. See tests/fixtures/README.md.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def __truediv__(self, name: str) -> Path:
        path = self.root / name
        if not path.exists():
            pytest.skip(f"sample PDF '{name}' is not present (kept out of git, see tests/fixtures/README.md)")
        return path


@pytest.fixture(scope="session")   # one value for the whole test run: the folder never changes
def fixtures_dir() -> SampleDir:
    return SampleDir(FIXTURES)


@pytest.fixture
def make_line():
    """Factory fixture: make_line(x0, y0, x1, y1, size=10, text='...') -> Line."""
    def _make(x0, y0, x1, y1, size=10.0, text=None, font="Body"):
        return Line((x0, y0, x1, y1), size, text, font)
    return _make


@pytest.fixture
def fake_page(make_line):
    """A tiny synthetic two-story page. No PDF, no OCR: runs in microseconds.

        +------------------------------+
        |  BIG STORY HEADLINE (size 30)|   <- spans both columns
        |  col A (5 lines) | col B (5) |
        |  LEFT STORY (size 24)        |   <- left column only
        |  col A (4 lines)             |
        +------------------------------+
    """
    lines = [make_line(0, 0, 210, 30, size=30, text="Big story headline")]
    for i in range(5):
        y = 40 + i * 12
        lines.append(make_line(0, y, 100, y + 10, text=f"A{i} words in left column"))
        lines.append(make_line(110, y, 210, y + 10, text=f"B{i} words in right column"))
    lines.append(make_line(0, 150, 100, 174, size=24, text="Left story"))
    for i in range(4):
        y = 180 + i * 12
        lines.append(make_line(0, y, 100, y + 10, text=f"C{i} lower left"))
    return lines

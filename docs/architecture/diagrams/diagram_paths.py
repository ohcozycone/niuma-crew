"""Locate current and proposed diagram outputs after documentation moves."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def destination(name):
    if name == "backend-current":
        target = ROOT / "docs/architecture/diagrams" / f"{name}.svg"
    elif name == "backend-modules":
        target = ROOT / "docs/proposals/backend-architecture/diagrams" / f"{name}.svg"
    else:
        target = Path(__file__).parent / f"{name}.svg"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target

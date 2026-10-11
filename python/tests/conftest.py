from __future__ import annotations

import json
from functools import partial
from pathlib import Path

import pytest

from cld_reducer import _solver, canonical, reduction

CONFORMANCE = Path(__file__).resolve().parents[2] / "conformance"


def fixture_cases(kind: str) -> list[dict]:
    """Cases of one conformance fixture file.

    When the whole fixtures folder is absent (an unpacked sdist) there are none; a missing
    file in a present folder fails.
    """
    if not (CONFORMANCE / "fixtures").exists():
        return []
    text = (CONFORMANCE / "fixtures" / f"{kind}.json").read_text(encoding="utf-8")
    return json.loads(text)["cases"]


needs_conformance = pytest.mark.skipif(
    not (CONFORMANCE / "fixtures").exists(), reason="conformance/ is not available"
)


@pytest.fixture(params=["on", "off"], ids=["presolve-on", "presolve-off"])
def presolve(request: pytest.FixtureRequest):
    """Run a test with HiGHS presolve on and again with it off."""
    old = _solver.settings.presolve
    _solver.settings.presolve = request.param
    yield request.param
    _solver.settings.presolve = old


@pytest.fixture
def reference_engine(monkeypatch):
    """Keep solver fault tests reachable on inputs that now have a certificate."""
    monkeypatch.setattr(
        reduction, "_solve_canonical", partial(canonical._solve_canonical, _certificate=False)
    )

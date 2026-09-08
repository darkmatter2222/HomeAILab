import importlib.util
import sys
from pathlib import Path

# Load tools/acceptance.py as a module (it is a script, not a package).
_SPEC = importlib.util.spec_from_file_location(
    "opendeck_acceptance", Path(__file__).resolve().parent.parent / "tools" / "acceptance.py"
)
_am = importlib.util.module_from_spec(_SPEC)
sys.modules["opendeck_acceptance"] = _am
_SPEC.loader.exec_module(_am)


def test_matrix_is_nontrivial():
    rows = _am.build_matrix()
    assert len(rows) >= 24
    kinds = {r.kind for r in rows}
    assert "headless" in kinds


def test_all_headless_rows_pass():
    failures = []
    for row in _am.build_matrix():
        h = _am.build()
        try:
            row.run(h)
        except Exception as e:  # noqa: BLE001
            failures.append(f"{row.id}: {e!r}")
    assert not failures, "\n".join(failures)


def test_physical_rows_are_listed_and_distinct():
    assert len(_am.PHYSICAL) >= 6
    # physical rows are the ones NOT covered by the headless matrix
    headless_ids = {r.id for r in _am.build_matrix()}
    physical_ids = {p[0] for p in _am.PHYSICAL}
    assert headless_ids.isdisjoint(physical_ids)

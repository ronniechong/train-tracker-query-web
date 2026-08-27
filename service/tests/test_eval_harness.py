"""M03 decision-gate checks. Hits live Groq + train-tracker - never runs by
default (see the "eval" marker in pyproject.toml). Run on demand:

    pytest -m eval tests/test_eval_harness.py -v
"""

import pytest

from eval import harness

pytestmark = pytest.mark.eval

_SEEDED_REGRESSIONS = {"Richmond", "North", "South", "East", "West"}


async def test_extraction_golden_set():
    cases = harness.load_extraction_golden()
    failures = []
    for case in cases:
        matched, actual = await harness.run_extraction_case(case)
        if not matched:
            failures.append((case["transcript"], case["expected"], actual))

    pass_rate = (len(cases) - len(failures)) / len(cases)
    detail = "\n".join(f"  {t!r}\n    expected={e}\n    actual  ={a}" for t, e, a in failures)
    assert pass_rate >= 0.90, f"{pass_rate:.0%} pass rate (need >=90%). Failures:\n{detail}"


async def test_stt_mishear_set():
    cases = harness.load_stt_mishear()
    failures = []
    seeded_failures = []
    for case in cases:
        matched, actual = await harness.run_mishear_case(case)
        if not matched:
            entry = (case["spoken"], case["expected_outcome"], actual)
            failures.append(entry)
            if case["spoken"] in _SEEDED_REGRESSIONS:
                seeded_failures.append(entry)

    detail = "\n".join(f"  {s!r} expected={e} actual={a}" for s, e, a in failures)
    assert not seeded_failures, (
        f"Seeded regression(s) failed - this means the eval harness or a "
        f"real fix regressed, not a tuning target:\n{detail}"
    )
    pass_rate = (len(cases) - len(failures)) / len(cases)
    assert pass_rate >= 0.85, f"{pass_rate:.0%} pass rate (need >=85%). Failures:\n{detail}"


async def test_end_to_end_set():
    cases = harness.load_end_to_end()
    failures = []
    for case in cases:
        matched, resp = await harness.run_end_to_end_case(case)
        if not matched:
            failures.append((case["transcript"], case["expected_category"], harness.classify_outcome(resp)))

    pass_rate = (len(cases) - len(failures)) / len(cases)
    detail = "\n".join(f"  {t!r} expected={e} actual={a}" for t, e, a in failures)
    assert pass_rate >= 0.90, f"{pass_rate:.0%} pass rate (need >=90%). Failures:\n{detail}"


async def test_judge_vs_manual_sanity_check():
    """The end-to-end set doubles as the manual-review sample (>=15
    required) - each answer here has already been manually reviewed
    against expected_category/expected_fields when the set was curated."""
    cases = harness.load_end_to_end()
    assert len(cases) >= 15, "manual-review sample must be at least 15 cases"

    disagreements = []
    for case in cases:
        matched, resp = await harness.run_end_to_end_case(case)
        verdict = await harness.grade_end_to_end_case(case, resp)
        # The judge disagrees with manual review if it fails a case that
        # actually matched the expected outcome, or passes one that didn't.
        if verdict.overall_pass != matched:
            disagreements.append((case["transcript"], matched, verdict.overall_pass, verdict.notes))

    agreement_rate = (len(cases) - len(disagreements)) / len(cases)
    detail = "\n".join(
        f"  {t!r} manual={m} judge={j} notes={n!r}" for t, m, j, n in disagreements
    )
    assert agreement_rate >= 0.85, f"{agreement_rate:.0%} agreement (need >=85%). Disagreements:\n{detail}"

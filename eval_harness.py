"""
eval_harness.py — PawPal+ Evaluation Harness (Stretch Feature)

Runs the full system (scheduling + AI advisor) on predefined scenarios and prints
a structured pass/fail report with confidence scores.

Usage:
    python eval_harness.py              # skips AI tests if ANTHROPIC_API_KEY not set
    ANTHROPIC_API_KEY=sk-... python eval_harness.py

Exit code: 0 if all tests pass, 1 otherwise.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Optional

from pawpal_system import Owner, Pet, Task, Scheduler, ScheduledTask
from ai_advisor import (
    get_care_guidelines,
    assess_schedule_feasibility,
    flag_health_concern,
)

# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    name: str
    passed: bool
    confidence: Optional[float] = None
    detail: str = ""


@dataclass
class HarnessReport:
    results: list[TestResult] = field(default_factory=list)

    def add(self, result: TestResult) -> None:
        self.results.append(result)
        status = "PASS" if result.passed else "FAIL"
        conf   = f"  confidence={result.confidence:.2f}" if result.confidence is not None else ""
        print(f"  [{status}] {result.name}{conf}")
        if result.detail:
            print(f"         {result.detail}")

    def summary(self) -> None:
        total  = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        confs  = [r.confidence for r in self.results if r.confidence is not None]
        avg_conf = sum(confs) / len(confs) if confs else None

        print("\n" + "=" * 60)
        print(f"Results: {passed}/{total} tests passed")
        if avg_conf is not None:
            print(f"Average AI confidence: {avg_conf:.2f}")
        print("=" * 60)

    def all_passed(self) -> bool:
        return all(r.passed for r in self.results)


# ── Helper ────────────────────────────────────────────────────────────────────

def _make_owner(hours: float) -> Owner:
    return Owner(name="TestOwner", available_hours=hours)


def _run(name: str, fn: Callable[[], TestResult]) -> TestResult:
    try:
        return fn()
    except Exception as exc:
        return TestResult(name=name, passed=False, detail=f"Exception: {exc}")


# ── Scheduling tests (no API key needed) ─────────────────────────────────────

def test_high_priority_fits_within_budget() -> TestResult:
    name = "Knapsack: high-priority task scheduled within 60-min budget"
    owner = _make_owner(1.0)  # 60 min
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    pet.add_task(Task(title="Walk",    task_type="walk", duration_minutes=45, priority="high"))
    pet.add_task(Task(title="Groom",   task_type="groom", duration_minutes=30, priority="low"))

    scheduler = Scheduler(owner=owner)
    plan = scheduler.generate_plan()

    if len(plan) == 1 and plan[0].task.title == "Walk":
        return TestResult(name=name, passed=True)
    return TestResult(name=name, passed=False,
                      detail=f"Got {[p.task.title for p in plan]} instead of ['Walk']")


def test_overdue_task_sorted_first() -> TestResult:
    name = "Sorting: overdue task appears before future task"
    owner = _make_owner(4.0)
    pet = Pet(name="Neko", species="cat")
    owner.add_pet(pet)
    today = date.today()
    pet.add_task(Task(title="Future feed", task_type="feed", duration_minutes=10,
                      priority="medium", deadline=today + timedelta(days=3)))
    pet.add_task(Task(title="Overdue meds", task_type="meds", duration_minutes=5,
                      priority="medium", deadline=today - timedelta(days=1)))

    scheduler = Scheduler(owner=owner)
    sorted_tasks = scheduler.get_tasks_sorted()
    first = sorted_tasks[0].title

    if first == "Overdue meds":
        return TestResult(name=name, passed=True)
    return TestResult(name=name, passed=False, detail=f"First task was '{first}'")


def test_recurring_task_rolls_over() -> TestResult:
    name = "Recurrence: daily task generates next occurrence after completion"
    owner = _make_owner(2.0)
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    today = date.today()
    pet.add_task(Task(title="Morning walk", task_type="walk", duration_minutes=60,
                      priority="high", frequency="daily", deadline=today))

    scheduler = Scheduler(owner=owner)
    scheduler.generate_plan()

    pending = pet.get_tasks(include_completed=False)
    if len(pending) == 1 and pending[0].deadline == today + timedelta(days=1):
        return TestResult(name=name, passed=True)
    return TestResult(name=name, passed=False,
                      detail=f"pending={[t.title for t in pending]}, deadlines={[str(t.deadline) for t in pending]}")


def test_conflict_detected() -> TestResult:
    name = "Conflict detection: overlapping slots produce a warning"
    owner = _make_owner(4.0)
    pet1 = Pet(name="Mochi", species="dog")
    pet2 = Pet(name="Neko",  species="cat")
    owner.add_pet(pet1)
    owner.add_pet(pet2)
    t1 = Task(title="Walk",  task_type="walk", duration_minutes=30, priority="high")
    t2 = Task(title="Feed",  task_type="feed", duration_minutes=30, priority="medium")
    pet1.add_task(t1)
    pet2.add_task(t2)

    start = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    end   = start + timedelta(minutes=30)
    scheduler = Scheduler(owner=owner)
    scheduler.scheduled_items = [
        ScheduledTask(task=t1, pet=pet1, start_time=start, end_time=end),
        ScheduledTask(task=t2, pet=pet2, start_time=start, end_time=end),
    ]
    warnings = scheduler.detect_conflicts()

    if warnings:
        return TestResult(name=name, passed=True)
    return TestResult(name=name, passed=False, detail="No conflicts detected — expected one.")


def test_zero_available_time_schedules_nothing() -> TestResult:
    name = "Edge case: 0 available hours schedules no tasks"
    owner = _make_owner(0.0)
    pet = Pet(name="Mochi", species="dog")
    owner.add_pet(pet)
    pet.add_task(Task(title="Walk", task_type="walk", duration_minutes=30, priority="high"))

    scheduler = Scheduler(owner=owner)
    plan = scheduler.generate_plan()

    if len(plan) == 0:
        return TestResult(name=name, passed=True)
    return TestResult(name=name, passed=False, detail=f"Got {len(plan)} scheduled item(s)")


# ── Local tool tests ──────────────────────────────────────────────────────────

def test_care_guidelines_dog_walk() -> TestResult:
    name = "Tool: get_care_guidelines returns content for dog/walk"
    result = get_care_guidelines("dog", "walk")
    if result and "dog" in result.lower() or "exercise" in result.lower() or "walk" in result.lower():
        return TestResult(name=name, passed=True)
    return TestResult(name=name, passed=False, detail=f"Got: {result[:80]}")


def test_schedule_feasibility_overrun() -> TestResult:
    name = "Tool: assess_schedule_feasibility flags overrun correctly"
    result = assess_schedule_feasibility(total_minutes=100, available_minutes=60)
    if not result["feasible"] and result["utilization"] > 1.0:
        return TestResult(name=name, passed=True)
    return TestResult(name=name, passed=False, detail=str(result))


def test_health_concern_joint_walk() -> TestResult:
    name = "Tool: flag_health_concern detects joint issue + walk"
    result = flag_health_concern(health_notes="mild arthritis in left hip",
                                  planned_tasks=["walk", "feed"])
    if result["has_concerns"] and any("joint" in c.lower() or "arthritis" in c.lower()
                                      for c in result["concerns"]):
        return TestResult(name=name, passed=True)
    return TestResult(name=name, passed=False, detail=str(result))


def test_health_concern_no_issue() -> TestResult:
    name = "Tool: flag_health_concern returns clean result for healthy pet"
    result = flag_health_concern(health_notes="", planned_tasks=["walk", "feed"])
    if not result["has_concerns"]:
        return TestResult(name=name, passed=True)
    return TestResult(name=name, passed=False, detail=str(result))


# ── AI advisor integration tests (require ANTHROPIC_API_KEY) ─────────────────

def test_ai_advisor_returns_advice(api_key: str) -> TestResult:
    name = "AI Advisor: generates advice with confidence score"
    from ai_advisor import PawPalAdvisor
    owner = _make_owner(2.0)
    pet = Pet(name="Mochi", species="dog", age=3)
    owner.add_pet(pet)
    pet.add_task(Task(title="Morning walk", task_type="walk", duration_minutes=30, priority="high"))

    scheduler = Scheduler(owner=owner)
    plan = scheduler.generate_plan(
        start_time=datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
    )

    advisor = PawPalAdvisor(api_key=api_key)
    result = advisor.advise(owner, plan)

    if result.advice and 0.0 <= result.confidence <= 1.0:
        return TestResult(name=name, passed=True, confidence=result.confidence,
                          detail=f"Tool calls: {len(result.tool_calls)}")
    return TestResult(name=name, passed=False, detail=f"advice={result.advice!r}, conf={result.confidence}")


def test_ai_advisor_calls_tools(api_key: str) -> TestResult:
    name = "AI Advisor: makes at least 2 tool calls (agentic loop)"
    from ai_advisor import PawPalAdvisor
    owner = _make_owner(3.0)
    pet = Pet(name="Neko", species="cat", age=2, health_notes="slight anxiety")
    owner.add_pet(pet)
    pet.add_task(Task(title="Feed",   task_type="feed",   duration_minutes=10, priority="high"))
    pet.add_task(Task(title="Enrich", task_type="enrich", duration_minutes=20, priority="medium"))

    scheduler = Scheduler(owner=owner)
    plan = scheduler.generate_plan(
        start_time=datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
    )

    advisor = PawPalAdvisor(api_key=api_key)
    result = advisor.advise(owner, plan)

    if len(result.tool_calls) >= 2:
        return TestResult(name=name, passed=True, confidence=result.confidence,
                          detail=f"Calls: {[tc['tool'] for tc in result.tool_calls]}")
    return TestResult(name=name, passed=False,
                      detail=f"Only {len(result.tool_calls)} tool call(s): {[tc['tool'] for tc in result.tool_calls]}")


def test_ai_advisor_health_concern_detected_in_advice(api_key: str) -> TestResult:
    name = "AI Advisor: advice mentions health concern for arthritic pet"
    from ai_advisor import PawPalAdvisor
    owner = _make_owner(2.0)
    pet = Pet(name="Buddy", species="dog", age=10, health_notes="severe arthritis, limping")
    owner.add_pet(pet)
    pet.add_task(Task(title="Long hike", task_type="walk", duration_minutes=90, priority="medium"))

    scheduler = Scheduler(owner=owner)
    plan = scheduler.generate_plan(
        start_time=datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
    )

    advisor = PawPalAdvisor(api_key=api_key)
    result = advisor.advise(owner, plan)

    advice_lower = result.advice.lower()
    concern_words = ("arthritis", "joint", "gentle", "limit", "caution", "careful", "health")
    if any(w in advice_lower for w in concern_words):
        return TestResult(name=name, passed=True, confidence=result.confidence)
    return TestResult(name=name, passed=False,
                      detail=f"No health-concern language found. Advice: {result.advice[:200]}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    report = HarnessReport()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    print("=" * 60)
    print("PawPal+ Evaluation Harness")
    print("=" * 60)

    print("\n[1/3] Scheduling tests")
    for fn in [
        test_high_priority_fits_within_budget,
        test_overdue_task_sorted_first,
        test_recurring_task_rolls_over,
        test_conflict_detected,
        test_zero_available_time_schedules_nothing,
    ]:
        report.add(_run(fn.__name__, fn))

    print("\n[2/3] Local tool tests")
    for fn in [
        test_care_guidelines_dog_walk,
        test_schedule_feasibility_overrun,
        test_health_concern_joint_walk,
        test_health_concern_no_issue,
    ]:
        report.add(_run(fn.__name__, fn))

    print("\n[3/3] AI Advisor integration tests")
    if not api_key:
        print("  (skipped — ANTHROPIC_API_KEY not set)")
    else:
        for fn in [
            test_ai_advisor_returns_advice,
            test_ai_advisor_calls_tools,
            test_ai_advisor_health_concern_detected_in_advice,
        ]:
            report.add(_run(fn.__name__, lambda f=fn: f(api_key)))

    report.summary()
    return 0 if report.all_passed() else 1


if __name__ == "__main__":
    sys.exit(main())

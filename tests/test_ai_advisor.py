"""Unit tests for the local tool functions in ai_advisor.py (no API key needed)."""
from ai_advisor import get_care_guidelines, assess_schedule_feasibility, flag_health_concern


# ── get_care_guidelines ───────────────────────────────────────────────────────

def test_care_guidelines_known_pair():
    result = get_care_guidelines("dog", "walk")
    assert isinstance(result, str) and len(result) > 10


def test_care_guidelines_case_insensitive():
    lower = get_care_guidelines("cat", "feed")
    upper = get_care_guidelines("Cat", "Feed")
    assert lower == upper


def test_care_guidelines_unknown_pair_returns_default():
    result = get_care_guidelines("parrot", "sing")
    assert "vet" in result.lower() or len(result) > 5


# ── assess_schedule_feasibility ───────────────────────────────────────────────

def test_feasibility_overrun_is_not_feasible():
    result = assess_schedule_feasibility(total_minutes=120, available_minutes=60)
    assert result["feasible"] is False
    assert result["utilization"] > 1.0


def test_feasibility_comfortable_is_feasible():
    result = assess_schedule_feasibility(total_minutes=30, available_minutes=60)
    assert result["feasible"] is True
    assert result["utilization"] < 1.0


def test_feasibility_tight_is_feasible():
    result = assess_schedule_feasibility(total_minutes=55, available_minutes=60)
    assert result["feasible"] is True


def test_feasibility_zero_available_handled():
    result = assess_schedule_feasibility(total_minutes=30, available_minutes=0)
    assert result["feasible"] is False


# ── flag_health_concern ───────────────────────────────────────────────────────

def test_health_concern_arthritis_with_walk():
    result = flag_health_concern("dog has arthritis", ["walk", "feed"])
    assert result["has_concerns"] is True
    assert len(result["concerns"]) >= 1


def test_health_concern_diet_with_feed():
    result = flag_health_concern("pet is overweight and on diet", ["feed"])
    assert result["has_concerns"] is True


def test_health_concern_medication_missing():
    result = flag_health_concern("takes daily medication", ["walk", "feed"])
    assert result["has_concerns"] is True
    assert any("medication" in c.lower() or "meds" in c.lower() for c in result["concerns"])


def test_health_concern_clean_notes_no_concern():
    result = flag_health_concern("", ["walk", "feed", "enrich"])
    assert result["has_concerns"] is False
    assert result["concerns"] == []


def test_health_concern_anxiety_suggests_enrichment():
    result = flag_health_concern("shows anxiety when alone", ["walk"])
    assert result["has_concerns"] is True
    assert any("enrich" in c.lower() or "anxiety" in c.lower() for c in result["concerns"])

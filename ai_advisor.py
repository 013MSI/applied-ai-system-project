"""
AI Advisor for PawPal+.

Implements an agentic workflow using the Anthropic Claude API.  Claude is given
a set of local tools (get_care_guidelines, assess_schedule_feasibility,
flag_health_concern) and iterates through a tool-use loop before producing a
final care recommendation with an explicit confidence score.

Usage (library):
    advisor = PawPalAdvisor()          # reads ANTHROPIC_API_KEY from env
    result  = advisor.advise(owner, scheduled_items)
    print(result["advice"])
    print(result["confidence"])

Usage (CLI demo):
    python ai_advisor.py
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

import anthropic

from pawpal_system import Owner, ScheduledTask

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)

# ---------------------------------------------------------------------------
# Local tool implementations
# These run entirely on the client side; results are fed back to Claude.
# ---------------------------------------------------------------------------

_CARE_GUIDELINES: dict[tuple[str, str], str] = {
    ("dog", "walk"):   "Dogs need 30–60 min of aerobic exercise daily. Morning and evening walks are ideal. Senior dogs or those with joint issues should stick to shorter, gentler outings on soft surfaces.",
    ("dog", "feed"):   "Feed adult dogs twice daily at consistent times. Measure portions to maintain healthy weight. Fresh water must always be available.",
    ("dog", "meds"):   "Administer medications at the same time each day. Some meds require food; follow vet instructions. Never skip doses — set reminders.",
    ("dog", "groom"):  "Brush coat 2–3× per week (daily for long-haired breeds). Trim nails monthly. Bathe every 4–8 weeks or as needed.",
    ("dog", "enrich"):  "Mental stimulation is as important as exercise. Puzzle feeders, scent games, and training sessions prevent boredom and destructive behaviour.",
    ("cat", "walk"):   "Cats can benefit from leashed walks or supervised outdoor time. Keep sessions short (10–20 min). Never force interaction with the outdoors.",
    ("cat", "feed"):   "Cats are obligate carnivores — feed high-protein food twice daily or via auto-feeder for free feeding. Avoid abrupt diet changes.",
    ("cat", "meds"):   "Pill pockets, pill guns, or compounded liquid formulations ease medication. Reward immediately after to reduce stress.",
    ("cat", "groom"):  "Most cats self-groom; assist long-haired cats with daily brushing. Check ears and trim nails every 2–3 weeks.",
    ("cat", "enrich"):  "Provide vertical space (cat trees), window perches, and interactive toys. Rotate toys to maintain novelty.",
}
_DEFAULT_GUIDELINE = "Follow your veterinarian's recommendations for this species and care type."


def get_care_guidelines(species: str, task_type: str) -> str:
    """Return evidence-based care guidelines for a species/task combination."""
    key = (species.strip().lower(), task_type.strip().lower())
    guideline = _CARE_GUIDELINES.get(key, _DEFAULT_GUIDELINE)
    logger.debug("get_care_guidelines(%s, %s) → %s", species, task_type, guideline[:60])
    return guideline


def assess_schedule_feasibility(total_minutes: int, available_minutes: int) -> dict[str, Any]:
    """Assess whether the schedule fits within the owner's daily time budget."""
    if available_minutes <= 0:
        return {"feasible": False, "utilization": 1.0, "message": "No available time specified."}
    utilization = round(total_minutes / available_minutes, 3)
    if utilization > 1.0:
        msg = f"Schedule overruns by {total_minutes - available_minutes} min — consider removing lower-priority tasks."
        feasible = False
    elif utilization >= 0.9:
        msg = "Schedule is tight (≥90% utilisation). Little room for overruns."
        feasible = True
    else:
        msg = f"Schedule is comfortable ({utilization:.0%} utilisation). Room for unexpected tasks."
        feasible = True
    logger.debug("assess_schedule_feasibility(%d/%d) → %s", total_minutes, available_minutes, msg)
    return {"feasible": feasible, "utilization": utilization, "message": msg}


def flag_health_concern(health_notes: str, planned_tasks: list[str]) -> dict[str, Any]:
    """Detect potential health-related scheduling conflicts from free-text notes."""
    concerns: list[str] = []
    notes = health_notes.lower()

    if any(w in notes for w in ("arthritis", "joint", "hip dysplasia", "limping")):
        if any(t in planned_tasks for t in ("walk", "run", "exercise")):
            concerns.append("Pet has joint issues — shorten walk duration and keep pace gentle.")

    if any(w in notes for w in ("diet", "weight", "obese", "overweight")):
        if "feed" in planned_tasks:
            concerns.append("Pet is on a weight-management diet — use measured portions only.")

    if any(w in notes for w in ("medication", "meds", "pills", "insulin", "prescription")):
        if "meds" not in planned_tasks:
            concerns.append("Health notes mention medication but no medication task is scheduled.")

    if any(w in notes for w in ("anxiety", "stress", "fearful", "reactive")):
        if "enrich" not in planned_tasks:
            concerns.append("Pet shows anxiety signs — enrichment activities can significantly reduce stress.")

    result = {
        "has_concerns": bool(concerns),
        "concerns": concerns,
        "recommendation": "; ".join(concerns) if concerns else "No health concerns detected for planned tasks.",
    }
    logger.debug("flag_health_concern → %s concern(s)", len(concerns))
    return result


# ---------------------------------------------------------------------------
# Tool registry used by the agentic loop
# ---------------------------------------------------------------------------

_TOOLS: list[dict] = [
    {
        "name": "get_care_guidelines",
        "description": (
            "Return evidence-based care guidelines for a specific pet species and care task type. "
            "Call this for every unique (species, task_type) pair in the schedule."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "species":   {"type": "string", "description": "e.g. 'dog' or 'cat'"},
                "task_type": {"type": "string", "description": "e.g. 'walk', 'feed', 'meds', 'groom', 'enrich'"},
            },
            "required": ["species", "task_type"],
        },
    },
    {
        "name": "assess_schedule_feasibility",
        "description": (
            "Check whether the total scheduled minutes fit within the owner's available minutes. "
            "Always call this once before giving your final recommendation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "total_minutes":     {"type": "integer", "description": "Sum of all scheduled task durations."},
                "available_minutes": {"type": "integer", "description": "Owner's total daily time budget in minutes."},
            },
            "required": ["total_minutes", "available_minutes"],
        },
    },
    {
        "name": "flag_health_concern",
        "description": (
            "Scan a pet's health notes against the list of planned task types and return any "
            "care-safety concerns. Call this for every pet that has non-empty health notes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "health_notes": {"type": "string", "description": "Free-text health notes for the pet."},
                "planned_tasks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of task_type strings planned for this pet.",
                },
            },
            "required": ["health_notes", "planned_tasks"],
        },
    },
]

_SYSTEM_PROMPT = """\
You are PawPal+, an expert AI pet care advisor integrated into a scheduling app.

Your job:
1. Use the provided tools to gather relevant care guidelines, check schedule feasibility, and flag any health concerns.
2. After collecting all necessary information via tools, write a concise, friendly care advisory (3–5 sentences).
3. End your final message with exactly one line in this format:
   Confidence: 0.XX
   (a decimal between 0.00 and 1.00 reflecting how confident you are in your advice given the available context)

Rules:
- Always call assess_schedule_feasibility before giving your final answer.
- Call get_care_guidelines for each unique species/task_type pair.
- Call flag_health_concern for any pet that has health notes.
- Do NOT ask clarifying questions — work with the information provided.
- Keep the advisory warm, practical, and owner-focused.
"""


@dataclass
class AdvisorResult:
    advice: str
    confidence: float
    tool_calls: list[dict]
    error: Optional[str] = None


class PawPalAdvisor:
    """Runs an agentic Claude loop to generate personalised pet care advice."""

    MAX_ITERATIONS = 10

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-haiku-4-5-20251001"):
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is not set. "
                "Export it before running: export ANTHROPIC_API_KEY=sk-ant-..."
            )
        self.client = anthropic.Anthropic(api_key=key)
        self.model = model

    def advise(self, owner: Owner, scheduled_items: list[ScheduledTask]) -> AdvisorResult:
        """Run the agentic tool-use loop and return a final AdvisorResult."""
        user_message = self._build_context(owner, scheduled_items)
        messages: list[dict] = [{"role": "user", "content": user_message}]
        tool_calls_log: list[dict] = []

        logger.info("AI Advisor starting — %d scheduled item(s) for %s", len(scheduled_items), owner.name)

        for iteration in range(self.MAX_ITERATIONS):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=_SYSTEM_PROMPT,
                tools=_TOOLS,
                messages=messages,
            )
            logger.info("Iteration %d: stop_reason=%s", iteration + 1, response.stop_reason)

            if response.stop_reason == "end_turn":
                advice_text = "".join(
                    block.text for block in response.content if hasattr(block, "text")
                ).strip()
                confidence = self._extract_confidence(advice_text)
                logger.info("Advice generated (confidence=%.2f): %s…", confidence, advice_text[:80])
                return AdvisorResult(
                    advice=advice_text,
                    confidence=confidence,
                    tool_calls=tool_calls_log,
                )

            if response.stop_reason == "tool_use":
                tool_results: list[dict] = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = self._execute_tool(block.name, block.input)
                        entry = {"tool": block.name, "input": block.input, "result": result}
                        tool_calls_log.append(entry)
                        logger.info("Tool call: %s(%s) → %s", block.name, block.input, str(result)[:120])
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result) if isinstance(result, dict) else str(result),
                        })
                messages.append({"role": "assistant", "content": response.content})
                messages.append({"role": "user", "content": tool_results})
                continue

            # Unexpected stop reason
            logger.warning("Unexpected stop_reason: %s", response.stop_reason)
            break

        return AdvisorResult(
            advice="Could not generate advice — maximum iterations reached.",
            confidence=0.0,
            tool_calls=tool_calls_log,
            error="max_iterations_exceeded",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_context(self, owner: Owner, scheduled_items: list[ScheduledTask]) -> str:
        lines = [
            f"Owner: {owner.name}",
            f"Available time today: {owner.available_hours:.1f} hours ({int(owner.available_hours * 60)} min)",
            "",
            "Pets:",
        ]
        for pet in owner.pets:
            lines.append(f"  • {pet.summary()}" + (f" — health notes: {pet.health_notes}" if pet.health_notes else ""))

        lines += ["", "Scheduled tasks:"]
        total_min = 0
        for item in scheduled_items:
            lines.append(
                f"  {item.start_time.strftime('%H:%M')}–{item.end_time.strftime('%H:%M')} "
                f"| {item.pet.name} | {item.task.title} ({item.task.task_type}) "
                f"[priority: {item.task.priority}, {item.task.duration_minutes} min]"
            )
            total_min += item.task.duration_minutes
        lines.append(f"\nTotal scheduled: {total_min} min")

        if not scheduled_items:
            lines.append("  (no tasks scheduled)")

        return "\n".join(lines)

    def _execute_tool(self, name: str, inputs: dict) -> Any:
        if name == "get_care_guidelines":
            return get_care_guidelines(**inputs)
        if name == "assess_schedule_feasibility":
            return assess_schedule_feasibility(**inputs)
        if name == "flag_health_concern":
            return flag_health_concern(**inputs)
        return {"error": f"Unknown tool: {name}"}

    def _extract_confidence(self, text: str) -> float:
        match = re.search(r"[Cc]onfidence:\s*(0?\.\d+|1\.0+|1)", text)
        if match:
            try:
                return min(1.0, max(0.0, float(match.group(1))))
            except ValueError:
                pass
        return 0.75  # sensible default if not found


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from datetime import datetime, timedelta
    from pawpal_system import Owner, Pet, Task, Scheduler

    demo_owner = Owner(name="Jordan", available_hours=3.0)
    mochi = Pet(name="Mochi", species="dog", age=5, health_notes="mild arthritis in left hip")
    neko  = Pet(name="Neko",  species="cat", age=2)

    demo_owner.add_pet(mochi)
    demo_owner.add_pet(neko)

    mochi.add_task(Task(title="Morning walk",  task_type="walk", duration_minutes=30, priority="high"))
    mochi.add_task(Task(title="Joint meds",    task_type="meds", duration_minutes=10, priority="high"))
    neko.add_task(Task( title="Breakfast feed", task_type="feed", duration_minutes=10, priority="medium"))
    neko.add_task(Task( title="Enrichment play", task_type="enrich", duration_minutes=15, priority="low"))

    scheduler = Scheduler(owner=demo_owner)
    plan = scheduler.generate_plan(
        start_time=datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
    )

    print("\n--- Schedule ---")
    for item in plan:
        print(f"  {item.start_time.strftime('%H:%M')} | {item.pet.name} | {item.task.title}")

    print("\n--- AI Advisor ---")
    try:
        advisor = PawPalAdvisor()
        result = advisor.advise(demo_owner, plan)
        print(f"\nTool calls made: {len(result.tool_calls)}")
        for tc in result.tool_calls:
            print(f"  • {tc['tool']}({tc['input']})")
        print(f"\nAdvice:\n{result.advice}")
        print(f"\nConfidence: {result.confidence:.2f}")
    except ValueError as exc:
        print(f"Skipped (no API key): {exc}")

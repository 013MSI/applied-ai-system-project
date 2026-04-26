# Model Card — PawPal+ AI Advisor

This document satisfies the HW4 requirement for a `model_card.md` covering
AI collaboration, limitations, bias, ethics, and testing reflections.

---

## 1. Model Details

| Field | Value |
|---|---|
| Model used | `claude-haiku-4-5-20251001` (Anthropic) |
| Interaction pattern | Agentic tool-use loop (multi-turn) |
| Local tools | `get_care_guidelines`, `assess_schedule_feasibility`, `flag_health_concern` |
| Output format | Free-text advice paragraph + `Confidence: 0.XX` line |
| Prompt caching | Not applied (short sessions; caching would help in high-volume deployments) |

---

## 2. Limitations and Biases

**Knowledge scope.** The local care-guidelines knowledge base covers only dogs
and cats with five task types. Exotic pets (rabbits, reptiles, birds) fall back
to a generic "follow your vet" message, which is safe but unhelpful.

**Health-note parsing is keyword-based.** `flag_health_concern` uses simple
string matching, not clinical NLP. It will miss paraphrases ("my dog hobbles"),
abbreviations, or non-English notes.

**No memory across sessions.** The AI Advisor has no long-term memory of past
schedules or the pet's history. Every call is stateless, so it cannot detect
*patterns* (e.g., "Mochi always misses meds on Mondays").

**LLM hallucination risk.** Even with grounded tool results, Claude can
occasionally state incorrect veterinary facts in its advisory text. The system
does not fact-check the LLM's prose against authoritative sources.

**Confidence score calibration.** The confidence value is self-reported by the
model and has not been calibrated against ground-truth outcomes. A score of 0.90
does not mean the advice is 90% accurate — it reflects Claude's subjective
certainty given the available context.

**Training data bias.** Claude was trained on internet-scale text, which
over-represents English-speaking, Western pet-keeping practices (e.g., large
dog breeds, indoor cats). Advice for working animals, farm animals, or
culturally specific practices may be less accurate.

---

## 3. Potential Misuse and Prevention

**Veterinary replacement risk.** Users might follow AI advice instead of
consulting a licensed vet for genuine health problems. The app includes a
disclaimer in the UI ("PawPal+ is not a substitute for professional veterinary
advice") and the advisor consistently references vets for health concerns.

**Scheduling overconfidence.** If an owner treats AI confidence scores as
objective accuracy guarantees, they might under-question harmful schedules
(e.g., a 90-min hike for an arthritic dog given a 0.85 confidence score).
Mitigation: the UI labels the metric "AI Confidence" and the README explains
what it means and what it does not mean.

**Data privacy.** Health notes entered into the app are sent to the Anthropic
API. Users should not enter personally identifiable information or sensitive
medical records. A production version should add a data-processing agreement
and a privacy notice.

---

## 4. Testing Reflections

**What surprised me:** The AI Advisor reliably identifies health concerns from
free-text notes even when the flag was set by the local `flag_health_concern`
tool (which uses simple keywords). What surprised me was that Claude *also*
paraphrased and extended those concerns in its advice — going beyond the tool
result to suggest specific mitigations (e.g., "soft terrain", "split the hike
into two sessions") that were not in any tool output. This emergent reasoning
was valuable but also unpredictable.

**Edge case that exposed a gap:** When `available_hours = 0`, the scheduler
produces an empty plan. The AI Advisor then calls `assess_schedule_feasibility`
with `total_minutes=0, available_minutes=0`, which hits the divide-by-zero
guard and returns a vague message. The resulting advice was generic and not
actionable. Fix: pass `available_minutes = max(1, ...)` in the context builder.

**Confidence calibration observation:** Confidence scores were highest (~0.90)
when the schedule was full and health notes were present — lots of context for
the model. Scores dropped to ~0.70 when the schedule was empty or the pet had
no health notes. This makes intuitive sense but needs formal calibration against
human-evaluated outputs before the score can be trusted as a reliability signal.

---

## 5. AI Collaboration During This Project

**Helpful suggestion:** When designing the agentic loop, Claude suggested
structuring the system prompt so the model is explicitly instructed to end its
*final* message with `Confidence: 0.XX` on its own line. This made confidence
extraction with a simple regex reliable across hundreds of test runs. Without
that instruction, the model sometimes embedded a confidence number mid-paragraph
in unpredictable formats.

**Flawed suggestion:** Claude initially proposed calling the Anthropic API once
per tool with a separate `client.messages.create()` call for each guideline
lookup ("one call per species/task pair for maximum accuracy"). This would have
cost 3–5× more tokens and added 3–5 extra round-trips per advisory session.
The correct approach — using Claude's native tool-use loop so a single agentic
session handles all tool calls — is both cheaper and architecturally cleaner.
I rejected the suggestion and implemented the loop pattern instead.

---

## 6. Portfolio Reflection

> *What this project says about me as an AI engineer.*

PawPal+ shows that I can take a working rule-based system and meaningfully
extend it with a real AI layer — not just a cosmetic chatbot wrapper, but a
structured agentic workflow that uses tools, reasons across multiple steps, and
explains itself. I treated AI as a component with known limitations (hallucination,
calibration uncertainty, static knowledge) rather than a magic oracle, and I
built tests to verify its behaviour at every layer. The gap between "the AI
sounds confident" and "the AI is accurate" is something I actively designed
against — through local tool grounding, structured output formats, and
transparent UI labelling. That engineering discipline, not just the API call,
is what defines responsible AI product work.

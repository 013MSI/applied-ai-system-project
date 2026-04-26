import os
import streamlit as st
from pawpal_system import Owner, Pet, Task, Scheduler

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

st.title("🐾 PawPal+")

st.markdown(
    """
Welcome to **PawPal+** — a pet care planning assistant that helps busy pet owners stay on top
of daily care tasks for their pets, powered by an AI advisor that reasons about your schedule.
"""
)

with st.expander("About this app", expanded=False):
    st.markdown(
        """
**PawPal+** helps a pet owner plan care tasks (walks, feeding, meds, grooming, enrichment)
based on constraints like available time, task priority, and deadlines.
The **AI Advisor** uses Claude's agentic tool-use loop to look up species-specific care
guidelines, check schedule feasibility, and flag any health concerns before giving advice.
"""
    )

# ── Session state ─────────────────────────────────────────────────────────────
if "owner" not in st.session_state:
    st.session_state.owner = Owner(name="Jordan", available_hours=8.0)
if "last_plan" not in st.session_state:
    st.session_state.last_plan = []

owner: Owner = st.session_state.owner

# ── Owner profile ─────────────────────────────────────────────────────────────
st.divider()
st.subheader("Owner")
owner.name = st.text_input("Owner name", value=owner.name)
owner.available_hours = st.number_input(
    "Available hours today", min_value=1.0, max_value=24.0, value=float(owner.available_hours)
)

# ── Add pet ───────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Add Pet")
new_pet_name    = st.text_input("Pet name",     value="", key="new_pet_name")
new_pet_species = st.selectbox("Species",       ["dog", "cat", "other"], key="new_pet_species")
new_pet_age     = st.number_input("Age",        min_value=0, max_value=30, value=0, key="new_pet_age")
new_pet_health  = st.text_input("Health notes (optional)", value="", key="new_pet_health")

if st.button("Add pet"):
    if new_pet_name.strip():
        if owner.get_pet(new_pet_name.strip()) is None:
            owner.add_pet(
                Pet(
                    name=new_pet_name.strip(),
                    species=new_pet_species,
                    age=int(new_pet_age),
                    health_notes=new_pet_health.strip(),
                )
            )
            st.success(f"Added pet: {new_pet_name.strip()}")
        else:
            st.warning(f"A pet named '{new_pet_name.strip()}' already exists.")
    else:
        st.error("Pet name cannot be empty.")

pet_names = [pet.name for pet in owner.pets]
if pet_names:
    st.write("**Current pets:**")
    for pet in owner.pets:
        notes = f" — {pet.health_notes}" if pet.health_notes else ""
        st.write(f"- {pet.summary()}{notes} — {len(pet.get_tasks())} pending task(s)")
else:
    st.info("No pets added yet.")

# ── Add task ──────────────────────────────────────────────────────────────────
st.divider()
st.subheader("Add Task")
if pet_names:
    selected_pet_name = st.selectbox("Assign to pet", pet_names, key="task_pet")
    task_title = st.text_input("Task title",        value="Morning walk", key="task_title")
    task_type  = st.selectbox("Task type",          ["walk", "feed", "meds", "groom", "enrich"], key="task_type")
    duration   = st.number_input("Duration (min)",  min_value=1, max_value=240, value=20, key="task_dur")
    priority   = st.selectbox("Priority",           ["low", "medium", "high"], index=1, key="task_pri")
    frequency  = st.selectbox("Frequency",          ["none", "daily", "weekly"], key="task_freq")

    if st.button("Add task"):
        pet = owner.get_pet(selected_pet_name)
        if pet is not None:
            pet.add_task(
                Task(
                    title=task_title,
                    task_type=task_type,
                    duration_minutes=int(duration),
                    priority=priority,
                    frequency=frequency,
                )
            )
            st.success(f"Task '{task_title}' added to {selected_pet_name}.")

    selected_pet = owner.get_pet(selected_pet_name)
    if selected_pet and selected_pet.tasks:
        st.write(f"**Tasks for {selected_pet.name}:**")
        st.table(
            [
                {
                    "Title":     t.title,
                    "Type":      t.task_type,
                    "Min":       t.duration_minutes,
                    "Priority":  t.priority,
                    "Frequency": t.frequency,
                    "Done":      t.completed,
                }
                for t in selected_pet.tasks
            ]
        )
else:
    st.info("Add a pet first before adding tasks.")

# ── Build schedule ────────────────────────────────────────────────────────────
st.divider()
st.subheader("Build Schedule")
if st.button("Generate schedule"):
    scheduler = Scheduler(owner=owner)

    pending = scheduler.get_tasks_sorted()
    if pending:
        st.markdown("#### Pending tasks (sorted by deadline → priority)")
        st.table(
            [
                {
                    "Pet":       next((p.name for p in owner.pets if t in p.tasks), "—"),
                    "Title":     t.title,
                    "Type":      t.task_type,
                    "Min":       t.duration_minutes,
                    "Priority":  t.priority,
                    "Deadline":  str(t.deadline) if t.deadline else "—",
                    "Frequency": t.frequency,
                }
                for t in pending
            ]
        )
    else:
        st.info("No pending tasks found.")

    plan = scheduler.generate_plan()
    st.session_state.last_plan = plan

    conflicts = scheduler.detect_conflicts()
    if conflicts:
        st.warning("⚠️ Conflicts detected in your schedule:")
        for warn in conflicts:
            st.warning(warn)
    else:
        st.success("✅ No conflicts detected in the planned schedule.")

    if not plan:
        st.info(scheduler.explain_plan())
    else:
        st.success(f"Today's Schedule — {len(plan)} task(s) scheduled")
        st.table(
            [
                {
                    "Start":    item.start_time.strftime("%H:%M"),
                    "End":      item.end_time.strftime("%H:%M"),
                    "Pet":      item.pet.name,
                    "Task":     item.task.title,
                    "Type":     item.task.task_type,
                    "Priority": item.task.priority,
                    "Reason":   item.reason,
                }
                for item in plan
            ]
        )
        st.metric("Plan score", f"{scheduler.score_plan():.0%}")
        st.write("**Explanation:**", scheduler.explain_plan())

# ── AI Advisor ────────────────────────────────────────────────────────────────
st.divider()
st.subheader("🤖 AI Care Advisor")
st.markdown(
    "The AI Advisor uses an **agentic workflow** — it calls local tools (care guidelines, "
    "feasibility check, health-concern detection) before producing personalised advice. "
    "Generate a schedule above, then click the button below."
)

api_key_input = st.text_input(
    "Anthropic API key (or set ANTHROPIC_API_KEY env var)",
    value=os.environ.get("ANTHROPIC_API_KEY", ""),
    type="password",
    key="api_key",
)

if st.button("Get AI advice"):
    plan = st.session_state.last_plan
    if not plan:
        st.warning("Generate a schedule first.")
    else:
        api_key = api_key_input.strip() or os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            st.error("No API key provided. Enter it above or export ANTHROPIC_API_KEY.")
        else:
            try:
                from ai_advisor import PawPalAdvisor
                with st.spinner("AI Advisor is thinking…"):
                    advisor = PawPalAdvisor(api_key=api_key)
                    result = advisor.advise(owner, plan)

                # Show tool-call trace (observable intermediate steps)
                with st.expander("🔍 Tool calls (agentic reasoning trace)", expanded=False):
                    for tc in result.tool_calls:
                        st.markdown(f"**`{tc['tool']}`** called with `{tc['input']}`")
                        st.json(tc["result"])

                st.info(result.advice)
                st.metric("AI Confidence", f"{result.confidence:.0%}")

                if result.error:
                    st.warning(f"Advisor warning: {result.error}")

            except Exception as exc:
                st.error(f"AI Advisor error: {exc}")

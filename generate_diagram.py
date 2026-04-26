"""
Generates assets/architecture.png — the PawPal+ system architecture diagram.
Run once: python generate_diagram.py
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

# ── Layout constants ──────────────────────────────────────────────────────────
FIG_W, FIG_H = 16, 11
BG   = "#F7F9FC"
COLS = {
    "user":    ("#4A90D9", "white"),   # blue
    "ui":      ("#5C6BC0", "white"),   # indigo
    "system":  ("#26A69A", "white"),   # teal
    "ai":      ("#EF5350", "white"),   # red
    "tools":   ("#FF7043", "white"),   # deep orange
    "cloud":   ("#AB47BC", "white"),   # purple
    "infra":   ("#78909C", "white"),   # blue-grey
    "out":     ("#66BB6A", "white"),   # green
    "test":    ("#FFA726", "white"),   # orange
}

def box(ax, x, y, w, h, label, sublabel, color_key, fontsize=9):
    fc, tc = COLS[color_key]
    rect = FancyBboxPatch(
        (x - w/2, y - h/2), w, h,
        boxstyle="round,pad=0.04",
        linewidth=1.5, edgecolor="white",
        facecolor=fc, zorder=3,
    )
    ax.add_patch(rect)
    ax.text(x, y + (0.09 if sublabel else 0), label,
            ha="center", va="center", color=tc,
            fontsize=fontsize, fontweight="bold", zorder=4)
    if sublabel:
        ax.text(x, y - 0.18, sublabel,
                ha="center", va="center", color=tc,
                fontsize=7.2, alpha=0.92, zorder=4)

def arrow(ax, x0, y0, x1, y1, label="", color="#555", rad=0.0):
    ax.annotate(
        "", xy=(x1, y1), xytext=(x0, y0),
        arrowprops=dict(
            arrowstyle="-|>", color=color, lw=1.4,
            connectionstyle=f"arc3,rad={rad}",
        ),
        zorder=2,
    )
    if label:
        mx, my = (x0+x1)/2, (y0+y1)/2
        ax.text(mx, my + 0.07, label, ha="center", va="bottom",
                fontsize=7, color=color, style="italic", zorder=5)

# ── Canvas ────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_xlim(0, FIG_W)
ax.set_ylim(0, FIG_H)
ax.axis("off")

# ── Title ─────────────────────────────────────────────────────────────────────
ax.text(FIG_W/2, 10.55, "PawPal+  —  System Architecture",
        ha="center", va="center", fontsize=15, fontweight="bold", color="#1A237E")
ax.text(FIG_W/2, 10.18, "HW4 · CodePath AI110 · Agentic Workflow with Claude API",
        ha="center", va="center", fontsize=9.5, color="#455A64")

# ── Node positions ────────────────────────────────────────────────────────────
# Row 1 (top): User → UI
U  = (2.0,  8.8)   # User
UI = (5.5,  8.8)   # Streamlit UI

# Row 2: PawPal System, AI Advisor side by side
PS = (2.8,  7.2)   # PawPal System
KS = (2.8,  5.8)   # Knapsack Scheduler
AI = (8.5,  7.2)   # AI Advisor

# Row 3: Tools (under AI)
T1 = (6.5,  5.5)   # get_care_guidelines
T2 = (8.5,  5.5)   # assess_schedule_feasibility
T3 = (10.5, 5.5)   # flag_health_concern

# Row 4: Claude API, Logger
CL = (11.8, 7.2)   # Claude API
LG = (11.8, 8.8)   # Logger

# Output
OUT = (5.5, 4.0)   # Schedule + AI Advice output

# Eval harness
EH  = (13.8, 5.5)  # Eval Harness
RPT = (13.8, 4.0)  # Test Report

# ── Draw nodes ────────────────────────────────────────────────────────────────
box(ax, *U,  1.5, 0.6, "User",            "pet owner",           "user",   10)
box(ax, *UI, 2.2, 0.6, "Streamlit UI",   "app.py",              "ui",     10)
box(ax, *PS, 2.4, 0.6, "PawPal System",  "pawpal_system.py",    "system", 9)
box(ax, *KS, 2.4, 0.65,"Knapsack Sched", "Priority · Conflicts · Score","system",8.5)
box(ax, *AI, 2.4, 0.65,"AI Advisor",     "ai_advisor.py — agentic loop","ai", 9)
box(ax, *T1, 2.2, 0.6, "get_care_",      "guidelines lookup",   "tools",  8)
box(ax, *T2, 2.2, 0.6, "assess_",        "time-budget check",   "tools",  8)
box(ax, *T3, 2.2, 0.6, "flag_health_",   "health-note patterns","tools",  8)
box(ax, *CL, 2.2, 0.65,"Claude API",     "claude-haiku-4-5",    "cloud",  9)
box(ax, *LG, 1.8, 0.55,"Logger",         "interaction logs",    "infra",  8.5)
box(ax, *OUT,2.6, 0.65,"Output",         "Schedule · Advice · Confidence","out",9)
box(ax, *EH, 1.9, 0.6, "Eval Harness",   "eval_harness.py",     "test",   8.5)
box(ax, *RPT,1.9, 0.6, "Test Report",    "Pass/Fail · Avg Conf","test",   8.5)

# ── Draw arrows ───────────────────────────────────────────────────────────────
C_FLOW  = "#37474F"
C_AI    = "#C62828"
C_TOOLS = "#BF360C"
C_CLOUD = "#6A1B9A"
C_INFRA = "#546E7A"
C_OUT   = "#2E7D32"
C_TEST  = "#E65100"

# User → UI
arrow(ax, U[0]+0.75, U[1], UI[0]-1.1, UI[1], "owner, pets, tasks", C_FLOW)
# UI → PawPal System
arrow(ax, UI[0]-0.3, UI[1]-0.3, PS[0]+0.3, PS[1]+0.3, "", C_FLOW, rad=-0.15)
# PawPal → Knapsack
arrow(ax, PS[0], PS[1]-0.33, KS[0], KS[1]+0.33, "", C_FLOW)
# Knapsack → UI (schedule back)
arrow(ax, KS[0]+0.5, KS[1]+0.2, UI[0]-0.5, UI[1]-0.3, "schedule", C_FLOW, rad=-0.2)
# UI → AI Advisor
arrow(ax, UI[0]+0.5, UI[1], AI[0]-1.2, AI[1], "schedule context", C_AI)
# AI → Tools
arrow(ax, AI[0]-0.6, AI[1]-0.33, T1[0]+0.1, T1[1]+0.3, "", C_TOOLS, rad=0.1)
arrow(ax, AI[0],     AI[1]-0.33, T2[0],     T2[1]+0.3, "", C_TOOLS)
arrow(ax, AI[0]+0.6, AI[1]-0.33, T3[0]-0.1, T3[1]+0.3, "", C_TOOLS, rad=-0.1)
# Tools → AI (results back)
arrow(ax, T1[0]+0.2, T1[1]+0.3, AI[0]-0.7, AI[1]-0.33, "", C_TOOLS, rad=-0.1)
arrow(ax, T2[0],     T2[1]+0.3, AI[0],     AI[1]-0.33, "", C_TOOLS)
arrow(ax, T3[0]-0.2, T3[1]+0.3, AI[0]+0.7, AI[1]-0.33, "", C_TOOLS, rad=0.1)
# AI ↔ Claude (double-headed via two arrows with rad)
arrow(ax, AI[0]+1.2, AI[1]+0.1, CL[0]-1.1, CL[1]+0.1, "tool_use",    C_CLOUD, rad=-0.25)
arrow(ax, CL[0]-1.1, CL[1]-0.1, AI[0]+1.2, AI[1]-0.1, "tool_result", C_CLOUD, rad=-0.25)
# AI → Logger
arrow(ax, AI[0]+0.8, AI[1]+0.25, LG[0]-0.9, LG[1]-0.25, "", C_INFRA)
# AI → advice → UI
arrow(ax, AI[0]-0.5, AI[1]-0.33, UI[0]+0.5, UI[1]-0.33, "advice + confidence", C_AI, rad=0.25)
# UI → Output
arrow(ax, UI[0], UI[1]-0.33, OUT[0], OUT[1]+0.33, "", C_OUT)
# Eval Harness
arrow(ax, EH[0]-0.95, EH[1]+0.05, PS[0]+1.3, PS[1]-0.1, "", C_TEST, rad=0.2)
arrow(ax, EH[0]-0.95, EH[1]-0.05, AI[0]+1.3, AI[1]-0.1, "", C_TEST, rad=-0.1)
arrow(ax, EH[0], EH[1]-0.33, RPT[0], RPT[1]+0.33, "", C_TEST)

# ── Legend ────────────────────────────────────────────────────────────────────
legend_items = [
    mpatches.Patch(color=COLS["user"][0],   label="User / Owner"),
    mpatches.Patch(color=COLS["ui"][0],     label="Streamlit UI (app.py)"),
    mpatches.Patch(color=COLS["system"][0], label="PawPal System"),
    mpatches.Patch(color=COLS["ai"][0],     label="AI Advisor (agentic loop)"),
    mpatches.Patch(color=COLS["tools"][0],  label="Local Tools (no API)"),
    mpatches.Patch(color=COLS["cloud"][0],  label="Claude API (cloud)"),
    mpatches.Patch(color=COLS["infra"][0],  label="Logging / Infra"),
    mpatches.Patch(color=COLS["out"][0],    label="Output"),
    mpatches.Patch(color=COLS["test"][0],   label="Eval Harness"),
]
ax.legend(handles=legend_items, loc="lower left", fontsize=8,
          framealpha=0.85, edgecolor="#B0BEC5",
          ncol=3, bbox_to_anchor=(0.01, 0.01))

plt.tight_layout(pad=0.3)
out_path = "assets/architecture.png"
fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=BG)
plt.close()
print(f"Saved: {out_path}")

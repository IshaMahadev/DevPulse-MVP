import pandas as pd
import os
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Path — update this to wherever your Excel file lives
EXCEL_PATH = os.path.join(os.path.dirname(__file__), "data", "intern_assignment_support_pack_dev_only_v3.xlsx")

_xl = None

def _load_excel():
    global _xl
    if _xl is None:
        _xl = pd.ExcelFile(EXCEL_PATH)
    return _xl


def _get_metrics_df():
    xl = _load_excel()
    raw = pd.read_excel(xl, sheet_name="Metric_Examples", header=None, skiprows=11)
    raw.columns = [
        "developer_id", "month", "developer_name", "manager_id", "team_name",
        "issues_done", "merged_prs", "prod_deployments", "escaped_bugs",
        "avg_cycle_time_days", "avg_lead_time_days", "bug_rate_pct",
        "pattern_hint", "dev_month_key"
    ]
    return raw.dropna(subset=["developer_id"])


def _get_developers_df():
    xl = _load_excel()
    return pd.read_excel(xl, sheet_name="Dim_Developers")


def get_all_developers():
    df = _get_developers_df()
    return df.rename(columns={
        "developer_id": "id",
        "developer_name": "name",
        "manager_id": "manager_id",
        "manager_name": "manager_name",
        "team_name": "team",
        "service_type": "service_type",
        "level": "level"
    }).to_dict(orient="records")


def get_all_months():
    df = _get_metrics_df()
    months = sorted([m for m in df["month"].unique().tolist() if str(m).startswith("20")])
    return {"months": months}


def get_metrics_for_developer(developer_id: str, month: str):
    df = _get_metrics_df()
    row = df[(df["developer_id"] == developer_id) & (df["month"] == month)]
    if row.empty:
        return None

    r = row.iloc[0]

    # Pull dev profile
    devs = _get_developers_df()
    dev_row = devs[devs["developer_id"] == developer_id]
    level = dev_row.iloc[0]["level"] if not dev_row.empty else "Unknown"

    metrics = {
        "lead_time_days": float(r["avg_lead_time_days"]),
        "cycle_time_days": float(r["avg_cycle_time_days"]),
        "pr_throughput": int(r["merged_prs"]),
        "deployment_frequency": int(r["prod_deployments"]),
        "bug_rate": float(r["bug_rate_pct"]),
    }

    interpretation = _build_interpretation(metrics, r["pattern_hint"])
    next_steps = _build_next_steps(metrics, r["pattern_hint"])
    tooltips = _build_tooltips(metrics)

    return {
        "developer_id": developer_id,
        "developer_name": r["developer_name"],
        "team": r["team_name"],
        "manager_id": r["manager_id"],
        "month": month,
        "level": level,
        "pattern": r["pattern_hint"],
        "metrics": metrics,
        "tooltips": tooltips,
        "interpretation": interpretation,
        "next_steps": next_steps,
    }


def _build_interpretation(m: dict, pattern: str) -> str:
    parts = []

    if m["lead_time_days"] <= 2.5:
        parts.append("Code is moving to production very quickly — the pipeline is healthy.")
    elif m["lead_time_days"] <= 4.0:
        parts.append("Lead time is moderate. There may be some delay in review or deployment stages.")
    else:
        parts.append("Lead time is high — code is taking longer than ideal to reach users after review opens.")

    if m["cycle_time_days"] <= 4.0:
        parts.append("Tasks are being completed at a good pace.")
    elif m["cycle_time_days"] <= 5.5:
        parts.append("Cycle time is slightly elevated — tickets may be larger or running into blockers.")
    else:
        parts.append("Cycle time is high, suggesting tickets may be too large or there are recurring blockers mid-sprint.")

    if m["bug_rate"] == 0:
        parts.append("No escaped bugs this month — quality looks solid.")
    elif m["bug_rate"] <= 0.3:
        parts.append("A small number of bugs escaped to production — worth investigating root causes.")
    else:
        parts.append("Bug rate is notable. Speed may be outpacing testing, or edge cases are being missed.")

    if m["deployment_frequency"] >= 3:
        parts.append("Deployment frequency is strong — shipping often and iterating fast.")
    elif m["deployment_frequency"] == 2:
        parts.append("Deploying at a steady pace, though there may be room to ship smaller changes more often.")
    else:
        parts.append("Low deployment frequency — could indicate large batched changes or blocked pipeline steps.")

    return " ".join(parts)


def _build_next_steps(m: dict, pattern: str) -> list:
    steps = []

    if m["cycle_time_days"] > 5.0:
        steps.append("Break tickets into smaller, self-contained chunks to reduce time spent on any single item.")

    if m["lead_time_days"] > 3.5:
        steps.append("Investigate where delay is happening: is code sitting in review, waiting for CI, or queued for deployment?")

    if m["bug_rate"] > 0.3:
        steps.append("Add a personal checklist before marking issues Done — edge cases and regression checks can catch escapes early.")
        steps.append("Review the root cause of recent bugs to spot patterns (test gaps, config issues, unclear requirements).")

    if m["pr_throughput"] < 2:
        steps.append("Consider splitting large PRs into smaller focused ones to speed up review cycles.")

    if m["deployment_frequency"] < 2:
        steps.append("Look at whether deployment gates (approvals, environment queues) can be streamlined.")

    default_steps = [
        "Maintain your current pace and review cadence.",
        "Consider mentoring a peer or documenting your workflow.",
        "Keep up the great communication and code quality."
    ]
    
    if len(steps) < 3:
        for ds in default_steps:
            if ds not in steps and len(steps) < 3:
                steps.append(ds)

    return steps[:3]


def _build_tooltips(m: dict) -> dict:
    def lead_time_status():
        v = m["lead_time_days"]
        if v <= 2.5:
            return f"{v} days — Excellent. Code reaches production very fast."
        elif v <= 4.0:
            return f"{v} days — Moderate. Some room to improve review or deploy speed."
        else:
            return f"{v} days — High. Investigate review wait time and deployment pipeline."

    def cycle_time_status():
        v = m["cycle_time_days"]
        if v <= 4.0:
            return f"{v} days — Good pace. Tickets are moving through efficiently."
        elif v <= 5.5:
            return f"{v} days — Slightly elevated. Consider ticket size and blockers."
        else:
            return f"{v} days — High. Tickets may be too large or blocked frequently."

    def pr_status():
        v = m["pr_throughput"]
        if v >= 4:
            return f"{v} PRs merged — Very active. High throughput this month."
        elif v >= 2:
            return f"{v} PRs merged — Steady output."
        else:
            return f"{v} PR(s) merged — Low activity. May indicate large-scope work or blockers."

    def deploy_status():
        v = m["deployment_frequency"]
        if v >= 3:
            return f"{v} deployments — Healthy release cadence."
        elif v == 2:
            return f"{v} deployments — Steady, but smaller batches could improve flow."
        else:
            return f"{v} deployment(s) — Infrequent. Check for pipeline or process bottlenecks."

    def bug_status():
        v = m["bug_rate"]
        if v == 0:
            return "0% — No escaped bugs. Quality is strong."
        elif v <= 0.3:
            return f"{v*100:.0f}% — A few bugs escaped. Worth reviewing root causes."
        else:
            return f"{v*100:.0f}% — Notable bug rate. Speed may be exceeding testing coverage."

    return {
        "lead_time_days": {
            "definition": "Average number of days from when a pull request is opened to when it successfully deploys to production.",
            "status": lead_time_status(),
        },
        "cycle_time_days": {
            "definition": "Average number of days from when a ticket moves to 'In Progress' to when it is marked 'Done'.",
            "status": cycle_time_status(),
        },
        "pr_throughput": {
            "definition": "Count of pull requests merged to the main branch this month.",
            "status": pr_status(),
        },
        "deployment_frequency": {
            "definition": "Count of successful production deployments this month.",
            "status": deploy_status(),
        },
        "bug_rate": {
            "definition": "Escaped production bugs found this month divided by total issues completed. A rate of 0.5 means 1 bug per 2 completed issues.",
            "status": bug_status(),
        },
    }


def get_manager_summary(month: str):
    df = _get_metrics_df()
    devs = _get_developers_df()
    month_df = df[df["month"] == month]
    if month_df.empty:
        return []

    results = []
    for _, row in month_df.iterrows():
        dev_row = devs[devs["developer_id"] == row["developer_id"]]
        level = dev_row.iloc[0]["level"] if not dev_row.empty else "N/A"
        results.append({
            "developer_id": row["developer_id"],
            "developer_name": row["developer_name"],
            "team": row["team_name"],
            "level": level,
            "pattern": row["pattern_hint"],
            "lead_time_days": float(row["avg_lead_time_days"]),
            "cycle_time_days": float(row["avg_cycle_time_days"]),
            "pr_throughput": int(row["merged_prs"]),
            "deployment_frequency": int(row["prod_deployments"]),
            "bug_rate": float(row["bug_rate_pct"]),
        })

    return sorted(results, key=lambda x: x["team"])

def get_developer_trend_plot(developer_id: str):
    df = _get_metrics_df()
    dev_df = df[df["developer_id"] == developer_id].sort_values("month")
    
    if dev_df.empty:
        return None
        
    months = dev_df["month"].tolist()
    lead_times = dev_df["avg_lead_time_days"].tolist()
    cycle_times = dev_df["avg_cycle_time_days"].tolist()
    
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(6, 4))
    
    # Premium Dark styling
    fig.patch.set_alpha(0.0)
    ax.patch.set_alpha(0.0)
    
    ax.plot(months, lead_times, marker='o', markersize=6, linewidth=2.5, label='Lead Time', color='#3B82F6', markerfacecolor='#0B0E14', markeredgecolor='#3B82F6', markeredgewidth=2)
    ax.plot(months, cycle_times, marker='o', markersize=6, linewidth=2.5, label='Cycle Time', color='#8B5CF6', markerfacecolor='#0B0E14', markeredgecolor='#8B5CF6', markeredgewidth=2, linestyle='-')
    
    ax.set_title(f"Trend for {developer_id}".upper(), fontdict={'fontsize': 12, 'fontweight': 'bold', 'color': '#F3F4F6'}, pad=15)
    ax.set_xlabel("MONTH", fontdict={'fontsize': 10, 'fontweight': 'bold', 'color': '#9CA3AF'}, labelpad=10)
    ax.set_ylabel("DAYS", fontdict={'fontsize': 10, 'fontweight': 'bold', 'color': '#9CA3AF'}, labelpad=10)
    
    # Clean spines
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_color('#ffffff1a')
    ax.spines['left'].set_color('#ffffff1a')
    ax.tick_params(colors='#9CA3AF', length=0)
    
    ax.legend(frameon=True, facecolor='#161b22cc', edgecolor='#ffffff1a', shadow=False, labelcolor='#F3F4F6')
    ax.grid(True, color='#ffffff0d', linestyle='-', linewidth=1)
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=120, transparent=True)
    buf.seek(0)
    plt.close(fig)
    return buf

import numpy as np

def get_team_comparison_plot(month: str):
    df = _get_metrics_df()
    month_df = df[df["month"] == month]
    
    if month_df.empty:
        return None
        
    grouped = month_df.groupby("team_name").agg({
        "avg_lead_time_days": "mean",
        "avg_cycle_time_days": "mean"
    }).reset_index()
    
    teams = grouped["team_name"].tolist()
    lead_times = grouped["avg_lead_time_days"].tolist()
    cycle_times = grouped["avg_cycle_time_days"].tolist()
    
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_alpha(0.0)
    ax.patch.set_alpha(0.0)
    
    x = np.arange(len(teams))
    width = 0.35
    
    ax.bar(x - width/2, lead_times, width, label='Avg Lead Time', color='#3B82F6', edgecolor='#0B0E14', linewidth=1.5)
    ax.bar(x + width/2, cycle_times, width, label='Avg Cycle Time', color='#8B5CF6', edgecolor='#0B0E14', linewidth=1.5)
    
    ax.set_title(f"TEAM COMPARISON - {month}".upper(), fontdict={'fontsize': 12, 'fontweight': 'bold', 'color': '#F3F4F6'}, pad=15)
    ax.set_ylabel("DAYS", fontdict={'fontsize': 10, 'fontweight': 'bold', 'color': '#9CA3AF'}, labelpad=10)
    ax.set_xticks(x)
    ax.set_xticklabels(teams, fontdict={'fontsize': 10, 'color': '#9CA3AF', 'fontweight': 'bold'})
    
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_color('#ffffff1a')
    ax.spines['left'].set_color('#ffffff1a')
    ax.tick_params(colors='#9CA3AF', length=0)
    
    ax.legend(frameon=True, facecolor='#161b22cc', edgecolor='#ffffff1a', shadow=False, labelcolor='#F3F4F6')
    ax.grid(True, axis='y', color='#ffffff0d', linestyle='-', linewidth=1)
    
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=120, transparent=True)
    buf.seek(0)
    plt.close(fig)
    return buf

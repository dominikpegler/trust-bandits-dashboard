"""Plotly adapters for the dashboard. Reuses the paper's color scheme."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

try:
    from trustbandits.constants import COLOR_EXPERT, COLOR_PEERS
except Exception:  # pragma: no cover - fallback if trustbandits not importable
    COLOR_EXPERT = "#3E5C76"
    COLOR_PEERS = "#E07A5F"

METRIC_LABELS = {
    "p_expert": "P(Expert)",
    "acc_expert": "Expert accuracy",
    "acc_peers": "Peers accuracy",
    "trust_expert": "Trust in Expert",
    "trust_peers": "Trust in Peers",
}


def heatmap_figure(
    pivot: pd.DataFrame,
    metric: str,
    title: str = "",
    zmin: float | None = None,
    zmax: float | None = None,
) -> go.Figure:
    """Heatmap of a metric over (c_pen x mu_E). Rows are c_pen (descending)."""
    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=[f"{c:.3g}" for c in pivot.columns],
            y=[f"{r:.3g}" for r in pivot.index],
            colorscale="RdBu_r",
            zmin=zmin,
            zmax=zmax,
            colorbar=dict(title=METRIC_LABELS.get(metric, metric)),
            hovertemplate="mu_E=%{x}<br>c_pen=%{y}<br>%{z:.3f}<extra></extra>",
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title="Evidence strength (mu_E)",
        yaxis_title="Asymmetric penalty (c_pen)",
        height=520,
        margin=dict(l=60, r=20, t=60, b=50),
    )
    return fig


def marginal_figure(
    df: pd.DataFrame,
    x: str,
    metric: str,
    title: str = "",
) -> go.Figure:
    """Line plot of a metric vs c_pen or mu_E, one line per other dimension."""
    fig = go.Figure()
    if df.empty:
        fig.add_annotation(text="No data for this selection", showarrow=False)
        return fig
    if x == "c_pen":
        group_col, line_col = "mu_e", "c_pen"
        xlabel = "Asymmetric penalty (c_pen)"
    else:
        group_col, line_col = "c_pen", "mu_e"
        xlabel = "Evidence strength (mu_E)"
    for g, gdf in df.groupby(group_col):
        gdf = gdf.sort_values(line_col)
        fig.add_trace(
            go.Scatter(
                x=gdf[line_col],
                y=gdf["value"],
                mode="lines+markers",
                name=f"{group_col}={g:.3g}",
                line=dict(width=2),
            )
        )
    fig.update_layout(
        title=title,
        xaxis_title=xlabel,
        yaxis_title=METRIC_LABELS.get(metric, metric),
        height=420,
        margin=dict(l=60, r=20, t=60, b=50),
    )
    return fig


def trajectory_figure(
    df: pd.DataFrame,
    metric: str,
    title: str = "",
) -> go.Figure:
    """Mean +/- SD ribbon over trials for a metric (Expert vs Peers)."""
    fig = go.Figure()
    if df.empty:
        fig.add_annotation(text="No trial data for this condition", showarrow=False)
        return fig
    if metric == "p_expert":
        fig.add_trace(
            go.Scatter(
                x=df["trial"], y=df["mean_p_expert"],
                mode="lines", name="P(Expert)",
                line=dict(color=COLOR_EXPERT, width=2.5),
                error_y=dict(type="data", array=df["sd_p_expert"], visible=True,
                             color="rgba(62,92,118,0.3)"),
            )
        )
    elif metric == "trust":
        for col, name, color in (
            ("mean_trust_expert", "Trust in Expert", COLOR_EXPERT),
            ("mean_trust_peers", "Trust in Peers", COLOR_PEERS),
        ):
            sd = df[col.replace("mean_", "sd_")]
            fig.add_trace(
                go.Scatter(
                    x=df["trial"], y=df[col], mode="lines", name=name,
                    line=dict(color=color, width=2.5),
                    error_y=dict(type="data", array=sd, visible=True,
                                 color="rgba(128,128,128,0.25)"),
                )
            )
    elif metric == "accuracy":
        for col, name, color in (
            ("mean_acc_expert", "Expert accuracy", COLOR_EXPERT),
            ("mean_acc_peers", "Peers accuracy", COLOR_PEERS),
        ):
            sd = df[col.replace("mean_", "sd_")]
            fig.add_trace(
                go.Scatter(
                    x=df["trial"], y=df[col], mode="lines", name=name,
                    line=dict(color=color, width=2.5),
                    error_y=dict(type="data", array=sd, visible=True,
                                 color="rgba(128,128,128,0.25)"),
                )
            )
    fig.update_layout(
        title=title,
        xaxis_title="Trial",
        yaxis_title=METRIC_LABELS.get(metric, metric),
        height=460,
        margin=dict(l=60, r=20, t=60, b=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    return fig

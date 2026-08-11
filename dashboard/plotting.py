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

# Heatmap tint alpha, matching the paper's p(Expert) heatmap
# (analysis_basemodel.py: cmap_alpha = 0.86). The clustering heatmap uses a
# more pastel 0.20; tune here to taste.
HEATMAP_ALPHA = 0.86

# Drop-shadow cast by fragility regions onto their neighbors, giving the
# regions a "raised" look. offset is the strip thickness in cell units;
# opacity is the shadow darkness.
PARADOX_SHADOW_OFFSET = 0.1
PARADOX_SHADOW_OPACITY = 0.28

METRIC_LABELS = {
    "p_expert": "p(Expert)",
    "acc_expert": "Expert accuracy",
    "acc_peers": "Peers accuracy",
    "trust_expert": "Trust in Expert",
    "trust_peers": "Trust in Peers",
}

# Greek-letter / subscript rendering for labels.
# Plotly supports HTML (<sub>), while Streamlit Markdown should use LaTeX.
_PLOT_MATH_MAP = {
    "mu_E": "μ<sub>E</sub>",
    "mu_e": "μ<sub>E</sub>",
    "c_pen": "c<sub>pen</sub>",
    "d_T": "d<sub>T</sub>",
    "dt": "d<sub>T</sub>",
    "rho_peers": "ρ<sub>peer</sub>",
    "rho_peer": "ρ<sub>peer</sub>",
    "rho_clust": "ρ<sub>clust</sub>",
    "rho": "ρ",
    "kappa": "κ",
    "tau": "τ",
    "sigma_E": "σ<sub>E</sub>",
    "sigma_expert": "σ<sub>expert</sub>",
    "sigma_peers_multiplier": "σ<sub>peers</sub>",
    "sigma": "σ",
    "lr_base": "α<sub>base</sub>",
    "f_peers": "f<sub>peers</sub>",
    "f_expert": "f<sub>expert</sub>",
    "m_peers": "m<sub>peers</sub>",
    "w_init_expert": "w<sub>0,expert</sub>",
    "w_init_peers": "w<sub>0,peers</sub>",
    "delta": "Δ",
    "P(Expert)": "p(Expert)",
}

_MD_MATH_MAP = {
    "mu_E": r"$\mu_E$",
    "mu_e": r"$\mu_E$",
    "c_pen": r"$c_{\mathrm{pen}}$",
    "d_T": r"$d_T$",
    "dt": r"$d_T$",
    "rho_peers": r"$\rho_{\mathrm{peer}}$",
    "rho_peer": r"$\rho_{\mathrm{peer}}$",
    "rho_clust": r"$\rho_{\mathrm{clust}}$",
    "rho": r"$\rho$",
    "kappa": r"$\kappa$",
    "tau": r"$\tau$",
    "sigma_E": r"$\sigma_E$",
    "sigma_expert": r"$\sigma_{\mathrm{expert}}$",
    "sigma_peers_multiplier": r"$\sigma_{\mathrm{peers}}$",
    "sigma": r"$\sigma$",
    "lr_base": r"$\alpha_{\mathrm{base}}$",
    "f_peers": r"$f_{\mathrm{peers}}$",
    "f_expert": r"$f_{\mathrm{expert}}$",
    "m_peers": r"$m_{\mathrm{peers}}$",
    "w_init_expert": r"$w_{0,\mathrm{expert}}$",
    "w_init_peers": r"$w_{0,\mathrm{peers}}$",
    "delta": r"$\Delta$",
    "P(Expert)": "p(Expert)",
}


def mathify(s: str) -> str:
    """Render common parameter tokens as HTML for Plotly/widget labels."""
    for k, v in _PLOT_MATH_MAP.items():
        s = s.replace(k, v)
    return s


def md_mathify(s: str) -> str:
    """Render common parameter tokens as Markdown/LaTeX for Streamlit text."""
    for k, v in _MD_MATH_MAP.items():
        s = s.replace(k, v)
    return s


# Source-aware metric -> the source whose color should dominate.
SOURCE_OF_METRIC = {
    "p_expert": None,  # bipolar: Peers at low values, Expert at high values
    "acc_expert": "expert",
    "acc_peers": "peers",
    "trust_expert": "expert",
    "trust_peers": "peers",
}


def _blend_white(hex_color: str, alpha: float = HEATMAP_ALPHA) -> str:
    """Blend a hex color toward white by `alpha` (0..1), like the paper's
    `LinearSegmentedColormap.from_list([color+aa, ...])` over a white figure."""
    c = hex_color.lstrip("#")
    r, g, b = (int(c[i : i + 2], 16) for i in (0, 2, 4))
    r = int(round(alpha * r + (1 - alpha) * 255))
    g = int(round(alpha * g + (1 - alpha) * 255))
    b = int(round(alpha * b + (1 - alpha) * 255))
    return f"#{r:02x}{g:02x}{b:02x}"


def _source_hex(source: str) -> str:
    return COLOR_EXPERT if source == "expert" else COLOR_PEERS


def _source_rgba(source: str, alpha: float) -> str:
    c = _source_hex(source).lstrip("#")
    r, g, b = (int(c[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


def heatmap_figure(
    pivot: pd.DataFrame,
    metric: str,
    title: str = "",
    zmin: float | None = None,
    zmax: float | None = None,
) -> go.Figure:
    """Heatmap of a metric over (c_pen x mu_E). Rows are c_pen (descending).

    Colors follow the paper: p(Expert) uses a Peers->Expert bipolar scale
    (Peers color dominates below 0.5, Expert above); source-specific metrics
    use that source's color as a single-hue sequential scale.
    """
    if zmin is None:
        zmin = 0.0
    if zmax is None:
        zmax = 1.0
    source = SOURCE_OF_METRIC.get(metric)
    if source is None:
        # bipolar Peers -> Expert (low p(Expert) = Peers favored)
        colorscale = [
            [0.0, _blend_white(COLOR_PEERS)],
            [1.0, _blend_white(COLOR_EXPERT)],
        ]
    else:
        # single-hue sequential in the owning source's color
        base = _source_hex(source)
        colorscale = [
            [0.0, _blend_white(base, alpha=0.15)],
            [1.0, _blend_white(base, alpha=HEATMAP_ALPHA)],
        ]
    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=[f"{c:.3g}" for c in pivot.columns],
            y=[f"{r:.3g}" for r in pivot.index],
            colorscale=colorscale,
            zmin=zmin,
            zmax=zmax,
            colorbar=dict(title=METRIC_LABELS.get(metric, metric), len=0.5),
            hovertemplate="μ<sub>E</sub>=%{x}<br>c<sub>pen</sub>=%{y}<br>%{z:.3f}<extra></extra>",
        )
    )
    fig.update_layout(
        title=title,
        xaxis_title=mathify("Evidence strength (mu_E)"),
        yaxis_title=mathify("Asymmetric penalty (c_pen)"),
        yaxis=dict(scaleanchor="x", scaleratio=1),
        height=700,
        margin=dict(l=60, r=20, t=60, b=50),
    )
    return fig


def marginal_figure(
    df: pd.DataFrame,
    x: str,
    metric: str,
    title: str = "",
) -> go.Figure:
    """Line plot of a metric vs c_pen or mu_E, one line per other dimension.

    Lines are colored by the metric's owning source (expert or peers), matching
    the analysis code's per-source color scheme.
    """
    fig = go.Figure()
    if df.empty:
        fig.add_annotation(text="No data for this selection", showarrow=False)
        return fig
    if x == "c_pen":
        group_col, line_col = "mu_e", "c_pen"
        xlabel = mathify("Asymmetric penalty (c_pen)")
    else:
        group_col, line_col = "c_pen", "mu_e"
        xlabel = mathify("Evidence strength (mu_E)")
    source = SOURCE_OF_METRIC.get(metric)
    if source is None:
        # p(Expert) is bipolar in heatmaps, but as a marginal line it is the
        # expert's quantity -> use the expert color.
        source = "expert" if metric == "p_expert" else None
    line_color = _source_hex(source) if source else "#333333"
    for g, gdf in df.groupby(group_col):
        gdf = gdf.sort_values(line_col)
        fig.add_trace(
            go.Scatter(
                x=gdf[line_col],
                y=gdf["value"],
                mode="lines+markers",
                name=f"{mathify(group_col)}={g:.3g}",
                line=dict(color=line_color, width=2),
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


def _add_paradox_shadow(
    fig: go.Figure,
    mask: np.ndarray,
    offset: float = PARADOX_SHADOW_OFFSET,
    opacity: float = PARADOX_SHADOW_OPACITY,
) -> None:
    """Cast a soft dark shadow from each fragility cell onto the cells below
    and to its right, so the region reads as sitting slightly higher.

    The shadow is drawn on top of the heatmap (the heatmap is a single opaque
    trace, so a shadow behind it would be invisible). The white outline is
    added afterwards so it stays on top of the shadow.
    """
    n_rows, n_cols = mask.shape
    fill = f"rgba(0,0,0,{opacity})"
    for i in range(n_rows):
        for j in range(n_cols):
            if not mask[i, j]:
                continue
            # The shadow is the region translated down-right by `offset`, minus
            # the region itself. Each translated cell splits into four
            # quadrants; we draw only the quadrants that land on non-fragility
            # cells. The top-left quadrant (inside cell (i,j)) is always
            # dropped, so the region's own cells are never darkened. The
            # right/bottom quadrants are inset by `offset` from the cell's own
            # edges, so adjacent cells' shadows meet edge-to-edge with no
            # overlap and no double-darkening along straight boundaries.
            if j + 1 < n_cols and not mask[i, j + 1]:
                fig.add_shape(
                    type="rect",
                    xref="x",
                    yref="y",
                    x0=j + 0.5,
                    x1=j + 0.5 + offset,
                    y0=i - 0.5 + offset,
                    y1=i + 0.5,
                    fillcolor=fill,
                    line=dict(width=0),
                )
            if i + 1 < n_rows and not mask[i + 1, j]:
                fig.add_shape(
                    type="rect",
                    xref="x",
                    yref="y",
                    x0=j - 0.5 + offset,
                    x1=j + 0.5,
                    y0=i + 0.5,
                    y1=i + 0.5 + offset,
                    fillcolor=fill,
                    line=dict(width=0),
                )
            if i + 1 < n_rows and j + 1 < n_cols and not mask[i + 1, j + 1]:
                fig.add_shape(
                    type="rect",
                    xref="x",
                    yref="y",
                    x0=j + 0.5,
                    x1=j + 0.5 + offset,
                    y0=i + 0.5,
                    y1=i + 0.5 + offset,
                    fillcolor=fill,
                    line=dict(width=0),
                )


def _add_paradox_boundaries(
    fig: go.Figure, mask: np.ndarray, color: str = "black", width: float = 1.0
) -> None:
    """Draw a white line on each fragility-cell edge that borders a non-fragility
    cell (or the grid edge), outlining each fragility region without internal lines."""
    n_rows, n_cols = mask.shape
    for i in range(n_rows):
        for j in range(n_cols):
            if not mask[i, j]:
                continue
            # top edge
            if i == 0 or not mask[i - 1, j]:
                fig.add_shape(
                    type="line",
                    xref="x",
                    yref="y",
                    x0=j - 0.5,
                    y0=i - 0.5,
                    x1=j + 0.5,
                    y1=i - 0.5,
                    line=dict(color=color, width=width),
                )
            # bottom edge
            if i == n_rows - 1 or not mask[i + 1, j]:
                fig.add_shape(
                    type="line",
                    xref="x",
                    yref="y",
                    x0=j - 0.5,
                    y0=i + 0.5,
                    x1=j + 0.5,
                    y1=i + 0.5,
                    line=dict(color=color, width=width),
                )
            # left edge
            if j == 0 or not mask[i, j - 1]:
                fig.add_shape(
                    type="line",
                    xref="x",
                    yref="y",
                    x0=j - 0.5,
                    y0=i - 0.5,
                    x1=j - 0.5,
                    y1=i + 0.5,
                    line=dict(color=color, width=width),
                )
            # right edge
            if j == n_cols - 1 or not mask[i, j + 1]:
                fig.add_shape(
                    type="line",
                    xref="x",
                    yref="y",
                    x0=j + 0.5,
                    y0=i - 0.5,
                    x1=j + 0.5,
                    y1=i + 0.5,
                    line=dict(color=color, width=width),
                )


def rounded_rect_path(x0, y0, x1, y1, radius):
    """Build an SVG path string for a rectangle with rounded corners."""
    r = radius
    return (
        f"M {x0+r},{y0} "
        f"L {x1-r},{y0} "
        f"Q {x1},{y0} {x1},{y0+r} "
        f"L {x1},{y1-r} "
        f"Q {x1},{y1} {x1-r},{y1} "
        f"L {x0+r},{y1} "
        f"Q {x0},{y1} {x0},{y1-r} "
        f"L {x0},{y0+r} "
        f"Q {x0},{y0} {x0+r},{y0} "
        f"Z"
    )


def base_paradox_heatmap_figure(
    df: pd.DataFrame,
    feedback_mode: str,
    representative_mu: float = 0.65,
    representative_c_pen: float = 6.0,
) -> go.Figure:
    """Paper-style base-model D1 heatmap.

    Color encodes p(Expert), text encodes accuracy gap Expert - Peers,
    elevated areas mark paradox cells, and the dark gray outline marks the
    selected condition used for dynamics.
    """
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data", showarrow=False)
        return fig
    mu_vals = sorted(df["mu_e"].unique())
    pen_vals = sorted(df["c_pen"].unique(), reverse=True)
    pivot = df.pivot(index="c_pen", columns="mu_e", values="mean_p_expert").loc[
        pen_vals, mu_vals
    ]
    delta = df.pivot(index="c_pen", columns="mu_e", values="delta_acc").loc[
        pen_vals, mu_vals
    ]
    acc_e = df.pivot(index="c_pen", columns="mu_e", values="mean_acc_expert").loc[
        pen_vals, mu_vals
    ]
    acc_p = df.pivot(index="c_pen", columns="mu_e", values="mean_acc_peers").loc[
        pen_vals, mu_vals
    ]
    paradox = (
        df.pivot(index="c_pen", columns="mu_e", values="is_paradox")
        .loc[pen_vals, mu_vals]
        .astype(bool)
    )
    mu_matrix = np.tile(np.array(mu_vals), (len(pen_vals), 1))
    pen_matrix = np.tile(np.array(pen_vals).reshape(-1, 1), (1, len(mu_vals)))
    custom = np.dstack(
        [mu_matrix, pen_matrix, acc_e.values, acc_p.values, delta.values]
    )
    x_pos = list(range(len(mu_vals)))
    y_pos = list(range(len(pen_vals)))
    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=x_pos,
            y=y_pos,
            colorscale=[
                [0.0, _blend_white(COLOR_PEERS)],
                [1.0, _blend_white(COLOR_EXPERT)],
            ],
            zmin=0,
            zmax=1,
            text=[[f"{v:+.2f}" for v in row] for row in delta.values],
            texttemplate="%{text}",
            textfont=dict(color="white"),
            customdata=custom,
            colorbar=dict(title="p(Expert)", len=0.5),
            hovertemplate=(
                "μ<sub>E</sub>=%{customdata[0]:.3g}<br>c<sub>pen</sub>=%{customdata[1]:.3g}<br>"
                "p(Expert)=%{z:.3f}<br>Expert accuracy=%{customdata[2]:.3f}"
                "<br>Peers accuracy=%{customdata[3]:.3f}<br>Δ accuracy=%{customdata[4]:+.3f}<extra></extra>"
            ),
        )
    )
    # Cast a drop shadow from each fragility region onto its neighbors so the
    # region reads as sitting slightly higher.
    _add_paradox_shadow(fig, paradox.values)
    # Draw a white outline around each fragility region (only edges bordering
    # non-fragility cells or the grid edge).
    _add_paradox_boundaries(fig, paradox.values)
    # Draw the selected-condition outline.
    for _, row in df.iterrows():
        x = mu_vals.index(row["mu_e"])
        y = pen_vals.index(row["c_pen"])
        if np.isclose(row["mu_e"], representative_mu) and np.isclose(
            row["c_pen"], representative_c_pen
        ):

            # regular rectangle
            # fig.add_shape(
            #     type="rect",
            #     xref="x",
            #     yref="y",
            #     x0=x - 0.6,
            #     x1=x + 0.6,
            #     y0=y - 0.6,
            #     y1=y + 0.6,
            #     line=dict(color="#1f1f1f", width=2),
            #     fillcolor="rgba(0,0,0,0)",
            # )

            # rectangle w/ rounded corners
            fig.add_shape(
                type="path",
                xref="x",
                yref="y",
                path=rounded_rect_path(
                    x - 0.44, y - 0.44, x + 0.44, y + 0.44, radius=0.18
                ),
                line=dict(color="#4f4f4f", width=2.5),
                fillcolor="rgba(0,0,0,0)",
            )

    fig.update_layout(
        title="",
        xaxis_title="Evidence strength (μ<sub>E</sub>)",
        yaxis_title="Asymmetric penalty (c<sub>pen</sub>)",
        xaxis=dict(
            tickmode="array", tickvals=x_pos, ticktext=[f"{x:.3g}" for x in mu_vals]
        ),
        yaxis=dict(
            tickmode="array",
            tickvals=y_pos,
            ticktext=[f"{y:.3g}" for y in pen_vals],
            autorange="reversed",
            scaleanchor="x",
            scaleratio=1,
        ),
        height=700,
        margin=dict(l=70, r=20, t=20, b=60),
    )
    return fig


def parameter_paradox_heatmap_figure(
    df: pd.DataFrame,
    x_label: str,
    y_label: str,
    title: str,
    selected_x: float | None = None,
    selected_y: float | None = None,
) -> go.Figure:
    """Generic paper-style p(Expert) heatmap with gap text and outlines."""
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data", showarrow=False)
        return fig
    x_vals = sorted(df["x"].unique())
    y_vals = sorted(df["y"].unique(), reverse=True)
    pivot = df.pivot(index="y", columns="x", values="value").loc[y_vals, x_vals]
    delta = df.pivot(index="y", columns="x", values="delta_acc").loc[y_vals, x_vals]
    acc_e = df.pivot(index="y", columns="x", values="mean_acc_expert_ss").loc[
        y_vals, x_vals
    ]
    acc_p = df.pivot(index="y", columns="x", values="mean_acc_peers_ss").loc[
        y_vals, x_vals
    ]
    paradox = (
        df.pivot(index="y", columns="x", values="is_paradox")
        .loc[y_vals, x_vals]
        .astype(bool)
    )
    x_matrix = np.tile(np.array(x_vals), (len(y_vals), 1))
    y_matrix = np.tile(np.array(y_vals).reshape(-1, 1), (1, len(x_vals)))
    custom = np.dstack([x_matrix, y_matrix, acc_e.values, acc_p.values, delta.values])
    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=list(range(len(x_vals))),
            y=list(range(len(y_vals))),
            colorscale=[
                [0.0, _blend_white(COLOR_PEERS)],
                [1.0, _blend_white(COLOR_EXPERT)],
            ],
            zmin=0,
            zmax=1,
            text=[[f"{v:+.2f}" for v in row] for row in delta.values],
            texttemplate="%{text}",
            textfont=dict(color="white"),
            customdata=custom,
            colorbar=dict(title="p(Expert)", len=0.5),
            hovertemplate=(
                f"{x_label}=%{{customdata[0]:.3g}}<br>{y_label}=%{{customdata[1]:.3g}}<br>"
                "p(Expert)=%{z:.3f}<br>Expert accuracy=%{customdata[2]:.3f}"
                "<br>Peers accuracy=%{customdata[3]:.3f}<br>Δ accuracy=%{customdata[4]:+.3f}<extra></extra>"
            ),
        )
    )
    # Cast a drop shadow from each fragility region onto its neighbors so the
    # region reads as sitting slightly higher.
    _add_paradox_shadow(fig, paradox.values)
    # Draw a white outline around each fragility region (only edges bordering
    # non-fragility cells or the grid edge).
    _add_paradox_boundaries(fig, paradox.values)
    # Draw the selected-condition outline.
    for _, row in df.iterrows():
        x = x_vals.index(row["x"])
        y = y_vals.index(row["y"])
        if (
            selected_x is not None
            and selected_y is not None
            and np.isclose(row["x"], selected_x)
            and np.isclose(row["y"], selected_y)
        ):
            # fig.add_shape(
            #     type="rect",
            #     xref="x",
            #     yref="y",
            #     x0=x - 0.52,
            #     x1=x + 0.52,
            #     y0=y - 0.52,
            #     y1=y + 0.52,
            #     line=dict(color="#3f3f3f", width=3.0),
            #     fillcolor="rgba(0,0,0,0)",
            # )

            # rectangle w/ rounded corners
            fig.add_shape(
                type="path",
                xref="x",
                yref="y",
                path=rounded_rect_path(
                    x - 0.44, y - 0.44, x + 0.44, y + 0.44, radius=0.18
                ),
                line=dict(color="#4f4f4f", width=2.5),
                fillcolor="rgba(0,0,0,0)",
            )

    fig.update_layout(
        title=title,
        xaxis_title=x_label,
        yaxis_title=y_label,
        xaxis=dict(
            tickmode="array",
            tickvals=list(range(len(x_vals))),
            ticktext=[f"{v:.3g}" for v in x_vals],
        ),
        yaxis=dict(
            tickmode="array",
            tickvals=list(range(len(y_vals))),
            ticktext=[f"{v:.3g}" for v in y_vals],
            autorange="reversed",
            scaleanchor="x",
            scaleratio=1,
        ),
        height=700,
        margin=dict(l=60, r=20, t=60 if title else 20, b=60),
    )
    return fig


def parameter_metric_heatmap_figure(
    df: pd.DataFrame,
    x_label: str,
    y_label: str,
    metric: str,
    title: str,
    selected_x: float | None = None,
    selected_y: float | None = None,
) -> go.Figure:
    """Generic metric heatmap over arbitrary parameter pairs."""
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="No data", showarrow=False)
        return fig
    x_vals = sorted(df["x"].unique())
    y_vals = sorted(df["y"].unique(), reverse=True)
    pivot = df.pivot(index="y", columns="x", values="value").loc[y_vals, x_vals]
    source = SOURCE_OF_METRIC.get(metric)
    if source is None:
        colorscale = [
            [0.0, _blend_white(COLOR_PEERS)],
            [1.0, _blend_white(COLOR_EXPERT)],
        ]
    else:
        base = _source_hex(source)
        colorscale = [[0.0, _blend_white(base, alpha=0.15)], [1.0, _blend_white(base)]]
    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values,
            x=list(range(len(x_vals))),
            y=list(range(len(y_vals))),
            colorscale=colorscale,
            zmin=0,
            zmax=1,
            text=[[f"{v:.2f}" for v in row] for row in pivot.values],
            texttemplate="%{text}",
            colorbar=dict(title=METRIC_LABELS.get(metric, metric), len=0.5),
            customdata=np.dstack(
                [
                    np.tile(np.array(x_vals), (len(y_vals), 1)),
                    np.tile(np.array(y_vals).reshape(-1, 1), (1, len(x_vals))),
                ]
            ),
            hovertemplate=(
                f"{x_label}=%{{customdata[0]:.3g}}<br>{y_label}=%{{customdata[1]:.3g}}<br>"
                f"{METRIC_LABELS.get(metric, metric)}=%{{z:.3f}}<extra></extra>"
            ),
        )
    )
    if selected_x is not None and selected_y is not None:
        for _, row in df.iterrows():
            if np.isclose(row["x"], selected_x) and np.isclose(row["y"], selected_y):
                x = x_vals.index(row["x"])
                y = y_vals.index(row["y"])
                # fig.add_shape(
                #     type="rect",
                #     xref="x",
                #     yref="y",
                #     x0=x - 0.52,
                #     x1=x + 0.52,
                #     y0=y - 0.52,
                #     y1=y + 0.52,
                #     line=dict(color="#1f1f1f", width=2.5),
                #     fillcolor="rgba(0,0,0,0)",
                # )
                # rectangle w/ rounded corners
                fig.add_shape(
                    type="path",
                    xref="x",
                    yref="y",
                    path=rounded_rect_path(
                        x - 0.44, y - 0.44, x + 0.44, y + 0.44, radius=0.18
                    ),
                    line=dict(color="#4f4f4f", width=2.5),
                    fillcolor="rgba(0,0,0,0)",
                )

    fig.update_layout(
        title=title,
        xaxis_title=x_label,
        yaxis_title=y_label,
        xaxis=dict(
            tickmode="array",
            tickvals=list(range(len(x_vals))),
            ticktext=[f"{v:.3g}" for v in x_vals],
        ),
        yaxis=dict(
            tickmode="array",
            tickvals=list(range(len(y_vals))),
            ticktext=[f"{v:.3g}" for v in y_vals],
            autorange="reversed",
            scaleanchor="x",
            scaleratio=1,
        ),
        height=700,
        margin=dict(l=60, r=20, t=60 if title else 20, b=60),
    )
    return fig


def _summary_ci(df: pd.DataFrame, x_col: str, value_col: str) -> pd.DataFrame:
    out = (
        df.groupby(x_col)[value_col]
        .agg(mean="mean", sd="std", n="count")
        .reset_index()
        .sort_values(x_col)
    )
    out["ci"] = 1.96 * out["sd"] / np.sqrt(out["n"])
    out["lo"] = (out["mean"] - out["ci"]).clip(0, 1)
    out["hi"] = (out["mean"] + out["ci"]).clip(0, 1)
    return out


def source_accuracy_by_mu_figure(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for value_col, name, src in (
        ("acc_expert", "Expert accuracy", "expert"),
        ("acc_peers", "Peers accuracy", "peers"),
    ):
        s = _summary_ci(df, "mu_e", value_col)
        fig.add_trace(
            go.Scatter(
                x=s["mu_e"],
                y=s["mean"],
                mode="lines+markers",
                name=name,
                line=dict(color=_source_hex(src), width=2),
                error_y=dict(
                    type="data",
                    array=s["ci"],
                    visible=True,
                    color=_source_rgba(src, 0.3),
                ),
            )
        )
    fig.update_layout(
        title="Source accuracy by evidence strength",
        xaxis_title="Evidence strength (μ<sub>E</sub>)",
        yaxis_title="Accuracy",
        yaxis=dict(range=[0, 1]),
        height=420,
        margin=dict(l=60, r=20, t=60, b=80),
        legend=dict(orientation="h", yanchor="top", y=-0.15),
    )
    return fig


def choice_area_ci_figure(
    df: pd.DataFrame, x_col: str, title: str, x_label: str
) -> go.Figure:
    s = _summary_ci(df, x_col, "p_expert")
    fig = go.Figure()
    x = s[x_col].to_numpy()
    fig.add_trace(
        go.Scatter(
            x=list(x) + list(x[::-1]),
            y=list(s["lo"]) + list(np.zeros(len(s))[::-1]),
            fill="toself",
            fillcolor=_source_rgba("expert", 0.60),
            line=dict(color="rgba(0,0,0,0)"),
            name="p(Expert)",
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=list(x) + list(x[::-1]),
            y=list(s["mean"]) + list(s["lo"][::-1]),
            fill="toself",
            fillcolor=_source_rgba("expert", 0.35),
            line=dict(color="rgba(0,0,0,0)"),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=list(x) + list(x[::-1]),
            y=list(s["hi"]) + list(s["mean"][::-1]),
            fill="toself",
            fillcolor=_source_rgba("peers", 0.35),
            line=dict(color="rgba(0,0,0,0)"),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=list(x) + list(x[::-1]),
            y=list(np.ones(len(s))) + list(s["hi"][::-1]),
            fill="toself",
            fillcolor=_source_rgba("peers", 0.60),
            line=dict(color="rgba(0,0,0,0)"),
            name="p(Peers)",
            hoverinfo="skip",
        )
    )
    gap = (
        df.assign(acc_gap=df["acc_expert"] - df["acc_peers"])
        .groupby(x_col)["acc_gap"]
        .mean()
        .reset_index()
    )
    fig.add_trace(
        go.Scatter(
            x=gap[x_col],
            y=gap["acc_gap"],
            mode="lines+markers",
            name="Δ accuracy",
            yaxis="y2",
            line=dict(color="gray", dash="dash", width=2),
        )
    )
    fig.add_hline(y=0.5, line_dash="dot", line_color="white")
    fig.update_layout(
        title=title,
        xaxis_title=x_label,
        yaxis_title="Choice probability",
        yaxis=dict(range=[0, 1]),
        yaxis2=dict(
            title="Δ accuracy",
            overlaying="y",
            side="right",
            range=[-0.5, 0.5],
            showgrid=False,
        ),
        height=420,
        margin=dict(l=60, r=60, t=60, b=80),
        legend=dict(orientation="h", yanchor="top", y=-0.15),
    )
    return fig


def error_locked_trust_figure(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for src, color in (("Expert", COLOR_EXPERT), ("Peers", COLOR_PEERS)):
        sub = df[df["source"] == src]
        if sub.empty:
            continue
        agg = (
            sub.groupby("offset")["trust_norm"]
            .agg(mean="mean", sd="std", n="count")
            .reset_index()
            .sort_values("offset")
        )
        ci = 1.96 * agg["sd"] / np.sqrt(agg["n"])
        fig.add_trace(
            go.Scatter(
                x=agg["offset"],
                y=agg["mean"],
                mode="lines",
                name=src,
                line=dict(color=color, width=2),
                error_y=dict(
                    type="data",
                    array=ci,
                    visible=True,
                    color=_source_rgba("expert" if src == "Expert" else "peers", 0.25),
                ),
            )
        )
    fig.add_vline(x=0, line_color="black", line_width=1)
    fig.add_hline(y=0, line_color="gray", line_dash="dot")
    fig.update_layout(
        title="Error-locked trust changes",
        xaxis_title="Trials relative to error",
        yaxis_title="Δ Trust",
        height=420,
        margin=dict(l=60, r=20, t=60, b=80),
        legend=dict(orientation="h", yanchor="top", y=-0.15),
    )
    return fig


def _ci(array, n_runs):
    """95% CI half-width from an SD across n_runs (matches the paper)."""
    return 1.96 * array / np.sqrt(n_runs)


def trajectory_figure(
    df: pd.DataFrame,
    metric: str,
    title: str = "",
    stats: dict | None = None,
    show_ci: bool | None = None,
) -> go.Figure:
    """Mean +/- 95% CI ribbon over trials for a metric (Expert vs Peers).

    Bands are 95% confidence intervals across runs (matching the paper).
    `stats` may carry {"steady": <float or (expert, peers)>, "full": ...} to be
    drawn as a text annotation (steady-state primary, full-range secondary).
    `show_ci` defaults to False when only one run is present (a CI from a
    single run is meaningless) and True otherwise.
    """
    fig = go.Figure()
    if df.empty:
        fig.add_annotation(text="No trial data for this condition", showarrow=False)
        return fig
    n_runs = int(df["n_runs"].iloc[0]) if "n_runs" in df.columns else 1
    if show_ci is None:
        show_ci = n_runs > 1
    if metric == "p_expert":
        fig.add_trace(
            go.Scatter(
                x=df["trial"],
                y=df["mean_p_expert"],
                mode="lines",
                name="p(Expert)",
                line=dict(color=COLOR_EXPERT, width=2.5),
                error_y=dict(
                    type="data",
                    array=_ci(df["sd_p_expert"], n_runs),
                    visible=show_ci,
                    color=_source_rgba("expert", 0.3),
                ),
            )
        )
    elif metric == "trust":
        for col, name, src in (
            ("mean_trust_expert", "Trust in Expert", "expert"),
            ("mean_trust_peers", "Trust in Peers", "peers"),
        ):
            sd = df[col.replace("mean_", "sd_")]
            fig.add_trace(
                go.Scatter(
                    x=df["trial"],
                    y=df[col],
                    mode="lines",
                    name=name,
                    line=dict(color=_source_hex(src), width=2.5),
                    error_y=dict(
                        type="data",
                        array=_ci(sd, n_runs),
                        visible=show_ci,
                        color=_source_rgba(src, 0.3),
                    ),
                )
            )
    elif metric == "accuracy":
        for col, name, src in (
            ("mean_acc_expert", "Expert accuracy", "expert"),
            ("mean_acc_peers", "Peers accuracy", "peers"),
        ):
            sd = df[col.replace("mean_", "sd_")]
            fig.add_trace(
                go.Scatter(
                    x=df["trial"],
                    y=df[col],
                    mode="lines",
                    name=name,
                    line=dict(color=_source_hex(src), width=2.5),
                    error_y=dict(
                        type="data",
                        array=_ci(sd, n_runs),
                        visible=show_ci,
                        color=_source_rgba(src, 0.3),
                    ),
                )
            )
    if stats:
        _add_stats_annotation(fig, metric, stats)
    fig.update_layout(
        title=title,
        xaxis_title="Trial",
        yaxis_title=METRIC_LABELS.get(metric, metric),
        height=460,
        margin=dict(l=60, r=20, t=60, b=80),
        legend=dict(orientation="h", yanchor="top", y=-0.15),
    )
    return fig


def _fmt(v) -> str:
    return "n/a" if v is None else f"{float(v):.3f}"


def _add_stats_annotation(fig: go.Figure, metric: str, stats: dict) -> None:
    """Draw steady-state (primary) and full-range (secondary) means."""
    steady = stats.get("steady")
    full = stats.get("full")
    if metric == "p_expert":
        lines = [
            f"Steady-state mean: <b>{_fmt(steady)}</b>",
            f"Full-range mean: {_fmt(full)}",
        ]
    else:
        labels = {"trust": ("Expert", "Peers"), "accuracy": ("Expert", "Peers")}[metric]
        s0, s1 = steady if isinstance(steady, (tuple, list)) else (None, None)
        f0, f1 = full if isinstance(full, (tuple, list)) else (None, None)
        lines = [
            f"{labels[0]}: SS <b>{_fmt(s0)}</b> / full {_fmt(f0)}",
            f"{labels[1]}: SS <b>{_fmt(s1)}</b> / full {_fmt(f1)}",
        ]
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0.02,
        y=0.97,
        xanchor="left",
        yanchor="top",
        align="left",
        text="<br>".join(lines),
        showarrow=False,
        font=dict(size=12, color="#333"),
        bordercolor="#999",
        borderwidth=1,
        borderpad=6,
        bgcolor="rgba(255,255,255,0.85)",
    )


def d5_bifurcation_figure(
    df: pd.DataFrame,
    clustering_levels: list,
    rho_levels: list,
    metric: str = "p_expert",
    title: str = "",
) -> go.Figure:
    """Grid of per-run distributions over (clustering x rho_peers).

    Each cell is a histogram of the per-run metric value, with a dashed line at
    0.5 for p(Expert). Mirrors the paper's D5 bifurcation figure.
    """
    from plotly.subplots import make_subplots

    n_rows, n_cols = len(clustering_levels), len(rho_levels)
    fig = make_subplots(
        rows=n_rows,
        cols=n_cols,
        shared_yaxes=True,
        shared_xaxes=True,
        horizontal_spacing=0.025,
        vertical_spacing=0.035,
    )
    for i, clust in enumerate(clustering_levels):
        for j, rho in enumerate(rho_levels):
            cell = df[(df["clustering"] == clust) & (df["rho_peers"] == rho)]
            if cell.empty:
                continue
            fig.add_trace(
                go.Histogram(
                    x=cell["value"],
                    nbinsx=30,
                    marker=dict(color=_source_hex("expert"), opacity=0.7),
                    showlegend=False,
                ),
                row=i + 1,
                col=j + 1,
            )
            if metric == "p_expert":
                fig.add_vline(
                    x=0.5, line_dash="dash", line_color="red", row=i + 1, col=j + 1
                )
    for j, rho in enumerate(rho_levels):
        fig.add_annotation(
            text=f"ρ<sub>peer</sub>={rho:.2f}",
            x=(j + 0.5) / n_cols,
            y=1.025,
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(size=12),
        )
    for i, clust in enumerate(clustering_levels):
        fig.add_annotation(
            text=f"ρ<sub>clust</sub>={clust:.2f}",
            x=-0.035,
            y=1 - (i + 0.5) / n_rows,
            xref="paper",
            yref="paper",
            textangle=-90,
            showarrow=False,
            font=dict(size=12),
        )
    fig.update_layout(
        title=title,
        height=300 * n_rows,
        margin=dict(l=80, r=20, t=90, b=60),
        showlegend=False,
    )
    fig.update_xaxes(title_text=METRIC_LABELS.get(metric, metric), row=n_rows)
    fig.update_yaxes(title_text="Runs", col=1)
    return fig

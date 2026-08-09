import numpy as np
import plotly.graph_objects as go
import streamlit as st

from . import loaders, plotting
from .ui import help_text, metadata_box


def _ci(sd, n_runs):
    return 1.96 * sd / np.sqrt(n_runs)


def _add_filled_band(fig, x, y0, y1, color, name=None, showlegend=False):
    fig.add_trace(
        go.Scatter(
            x=list(x) + list(x[::-1]),
            y=list(y1) + list(y0[::-1]),
            fill="toself",
            fillcolor=color,
            line=dict(color="rgba(0,0,0,0)"),
            hoverinfo="skip",
            name=name,
            showlegend=showlegend,
        )
    )


def hysteresis_trajectory_figure(df, meta, model_name, feedback, regime):
    fig = go.Figure()
    base = df[df["init_condition"] == "baseline"].sort_values("trial")
    post = df[df["init_condition"] == "post_collapse"].sort_values("trial")

    if not base.empty:
        x = base["trial"].to_numpy()
        mean = base["mean_p_expert"].to_numpy()
        ci = _ci(base["sd_p_expert"].to_numpy(), base["n_runs"].iloc[0])
        lo = np.clip(mean - ci, 0, 1)
        hi = np.clip(mean + ci, 0, 1)
        _add_filled_band(fig, x, np.zeros_like(lo), lo, plotting._source_rgba("expert", 0.60), "p(Expert), baseline", True)
        _add_filled_band(fig, x, lo, mean, plotting._source_rgba("expert", 0.35))
        _add_filled_band(fig, x, mean, hi, plotting._source_rgba("peers", 0.35))
        _add_filled_band(fig, x, hi, np.ones_like(hi), plotting._source_rgba("peers", 0.60), "p(Peers), baseline", True)

    if not post.empty:
        n_runs = post["n_runs"].iloc[0]
        ci = _ci(post["sd_p_expert"], n_runs)
        cutoff = int(post["trial"].max()) // 2
        ss_mean = post.loc[post["trial"] > cutoff, "mean_p_expert"].mean()
        fig.add_trace(
            go.Scatter(
                x=post["trial"],
                y=post["mean_p_expert"],
                mode="lines",
                line=dict(color=plotting._source_hex("expert"), width=2.5),
                error_y=dict(type="data", array=ci, visible=True, color=plotting._source_rgba("expert", 0.25)),
                name=f"p(Expert), post-collapse (M<sub>ss</sub>={ss_mean:.2f})",
            )
        )

    if regime == "cyclic" and meta:
        for it in range(meta["cycle_length"], meta["n_trials"] + 1, meta["cycle_length"]):
            fig.add_vline(x=it, line_dash="dash", line_color="white", line_width=1)

    fig.update_layout(
        title=f"Hysteresis trajectory · {model_name} · {regime} · feedback={feedback}",
        xaxis_title="Trial",
        yaxis_title="Choice probability",
        yaxis=dict(range=[0, 1]),
        height=520,
        margin=dict(l=60, r=20, t=60, b=100),
        legend=dict(orientation="h", yanchor="top", y=-0.18),
    )
    return fig


def render_extension_page(study: str):
    """Render a model-extension page.

    Currently the heatmap is the paper's middle slice (d_T x c_pen at fixed
    mu_E=0.65) because full mu_E-preserving extension aggregates are not yet
    ingested. Hysteresis is fully folded into the model page.
    """
    model_name = loaders.study_label(study)
    evaluation_mode = "binary" if study == "2" else "continuous"

    st.markdown(
        rf"""
This page shows the **{model_name}**. The parameter-landscape section follows
the paper's three heatmap slices: $\mu_E \times c_{{\mathrm{{pen}}}}$ at fixed
$d_T$, $d_T \times c_{{\mathrm{{pen}}}}$ at fixed $\mu_E$, and $d_T \times \mu_E$ at
fixed $c_{{\mathrm{{pen}}}}$.
"""
    )

    with st.sidebar:
        st.header("Controls")
        feedback = st.selectbox("Feedback mode", ["full", "partial"], help=help_text("feedback"))
        steady = st.checkbox(
            "Aggregate metric means over steady state (second half of trials)",
            value=True,
            help=help_text("aggregate_steady"),
        )
        st.caption("Affects only condition-level metric aggregation; trajectory panels still show full trial series.")
        levels = loaders.extension_levels(study, "cyclic", feedback)
        st.header("Selected condition")
        selected_mu = st.selectbox(
            "Evidence strength ($\\mu_E$)",
            levels["mu_e"],
            index=levels["mu_e"].index(0.65) if 0.65 in levels["mu_e"] else 0,
            help=help_text("mu_e"),
        )
        selected_d = st.selectbox(
            "Expert inertia ($d_T$)",
            levels["expert_inertia_divisor"],
            index=levels["expert_inertia_divisor"].index(2.0) if 2.0 in levels["expert_inertia_divisor"] else 0,
            help=help_text("d_t"),
        )
        selected_c_pen = st.selectbox(
            "Penalty ($c_{\\mathrm{pen}}$)",
            levels["c_pen"],
            index=levels["c_pen"].index(10.0) if 10.0 in levels["c_pen"] else 0,
            help=help_text("c_pen"),
        )
        hyst_regime = st.selectbox(
            "Hysteresis regime",
            ["cyclic", "stationary"],
            help=f"cyclic: {help_text('cyclic_regime')} stationary: {help_text('stationary_regime')}",
        )

    n_runs = loaders.condition_n_runs(
        study,
        feedback,
        evaluation_mode,
        "cyclic",
        selected_mu,
        selected_c_pen,
        selected_d,
    )
    metadata_box(
        [
            ("Model", model_name),
            ("Evaluation", evaluation_mode),
            ("Regime", "cyclic"),
            ("Feedback", feedback),
            ("N", f"{n_runs} simulations" if n_runs else "n/a"),
            ("Aggregation", "steady-state" if steady else "full-range"),
            ("Color", "p(Expert)"),
            ("Swept", "μ<sub>E</sub> × c<sub>pen</sub>, d<sub>T</sub> × c<sub>pen</sub>, d<sub>T</sub> × μ<sub>E</sub>"),
            ("Selected", f"μ<sub>E</sub>={selected_mu}, d<sub>T</sub>={selected_d:g}, c<sub>pen</sub>={selected_c_pen:g}"),
        ]
    )

    h1 = loaders.extension_heatmap_cells(
        study, feedback, "cyclic", x_var="mu_e", y_var="c_pen",
        fixed={"expert_inertia_divisor": selected_d}, steady=steady, metric="p_expert",
    )
    h2 = loaders.extension_heatmap_cells(
        study, feedback, "cyclic", x_var="expert_inertia_divisor", y_var="c_pen",
        fixed={"mu_e": selected_mu}, steady=steady, metric="p_expert",
    )
    h3 = loaders.extension_heatmap_cells(
        study, feedback, "cyclic", x_var="expert_inertia_divisor", y_var="mu_e",
        fixed={"c_pen": selected_c_pen}, steady=steady, metric="p_expert",
    )
    cols = st.columns(3)
    heatmaps = [
        (h1, "μ<sub>E</sub>", "c<sub>pen</sub>", f"fixed d<sub>T</sub>={selected_d:g}", selected_mu, selected_c_pen),
        (h2, "d<sub>T</sub>", "c<sub>pen</sub>", f"fixed μ<sub>E</sub>={selected_mu}", selected_d, selected_c_pen),
        (h3, "d<sub>T</sub>", "μ<sub>E</sub>", f"fixed c<sub>pen</sub>={selected_c_pen:g}", selected_d, selected_mu),
    ]
    for col, (data, xlab, ylab, title, sx, sy) in zip(cols, heatmaps):
        with col:
            if data.empty:
                st.warning("No data for this heatmap slice.")
            else:
                st.plotly_chart(
                    plotting.parameter_paradox_heatmap_figure(
                        data, x_label=xlab, y_label=ylab,
                        title=f"p(Expert) · {title}",
                        selected_x=sx, selected_y=sy,
                    ),
                    use_container_width=True,
                )

    with st.expander("Explore other metrics"):
        metric = st.selectbox(
            "Metric",
            ["acc_expert", "acc_peers", "trust_expert", "trust_peers"],
            format_func=lambda m: plotting.METRIC_LABELS.get(m, m),
        )
        e1 = loaders.extension_heatmap_cells(
            study, feedback, "cyclic", x_var="mu_e", y_var="c_pen",
            fixed={"expert_inertia_divisor": selected_d}, steady=steady, metric=metric,
        )
        e2 = loaders.extension_heatmap_cells(
            study, feedback, "cyclic", x_var="expert_inertia_divisor", y_var="c_pen",
            fixed={"mu_e": selected_mu}, steady=steady, metric=metric,
        )
        e3 = loaders.extension_heatmap_cells(
            study, feedback, "cyclic", x_var="expert_inertia_divisor", y_var="mu_e",
            fixed={"c_pen": selected_c_pen}, steady=steady, metric=metric,
        )
        cols = st.columns(3)
        for col, (data, xlab, ylab, title, sx, sy) in zip(
            cols,
            [
                (e1, "μ<sub>E</sub>", "c<sub>pen</sub>", f"fixed d<sub>T</sub>={selected_d:g}", selected_mu, selected_c_pen),
                (e2, "d<sub>T</sub>", "c<sub>pen</sub>", f"fixed μ<sub>E</sub>={selected_mu}", selected_d, selected_c_pen),
                (e3, "d<sub>T</sub>", "μ<sub>E</sub>", f"fixed c<sub>pen</sub>={selected_c_pen:g}", selected_d, selected_mu),
            ],
        ):
            with col:
                if data.empty:
                    st.warning("No data for this heatmap slice.")
                else:
                    st.plotly_chart(
                        plotting.parameter_metric_heatmap_figure(
                            data, x_label=xlab, y_label=ylab, metric=metric,
                            title=f"{plotting.METRIC_LABELS.get(metric, metric)} · {title}",
                            selected_x=sx, selected_y=sy,
                        ),
                        use_container_width=True,
                    )

    st.subheader("Selected condition dynamics")
    dyn = loaders.extension_trajectory_data(
        study, feedback, "cyclic", selected_mu, selected_d, selected_c_pen
    )
    if dyn.empty:
        st.warning("No extension trajectory data for the selected condition.")
    else:
        cutoff = int(dyn["trial"].max()) // 2
        ss = dyn[dyn["trial"] > cutoff]
        stats = {
            "p_expert": {
                "steady": ss["mean_p_expert"].mean(),
                "full": dyn["mean_p_expert"].mean(),
            },
            "trust": {
                "steady": (ss["mean_trust_expert"].mean(), ss["mean_trust_peers"].mean()),
                "full": (dyn["mean_trust_expert"].mean(), dyn["mean_trust_peers"].mean()),
            },
            "accuracy": {
                "steady": (ss["mean_acc_expert"].mean(), ss["mean_acc_peers"].mean()),
                "full": (dyn["mean_acc_expert"].mean(), dyn["mean_acc_peers"].mean()),
            },
        }
        st.plotly_chart(
            plotting.trajectory_figure(
                dyn, "trust",
                title=f"Selected condition trust · {model_name} · feedback={feedback}",
                stats=stats["trust"],
            ),
            use_container_width=True,
        )
        st.plotly_chart(
            plotting.trajectory_figure(
                dyn, "accuracy",
                title=f"Selected condition accuracy · {model_name} · feedback={feedback}",
                stats=stats["accuracy"],
            ),
            use_container_width=True,
        )
        st.plotly_chart(
            plotting.trajectory_figure(
                dyn, "p_expert",
                title=f"Selected condition p(Expert) · {model_name} · feedback={feedback}",
                stats=stats["p_expert"],
            ),
            use_container_width=True,
        )

    st.subheader("Hysteresis")
    traj = loaders.hysteresis_trajectory_data(study, feedback, hyst_regime)
    if traj.empty:
        st.warning("No hysteresis trajectory data for this selection.")
        return
    meta = loaders.hysteresis_condition_meta(study, feedback, hyst_regime)
    summary = loaders.hysteresis_data(study, feedback)
    if meta:
        mu_vals = " ↔ ".join(f"{x:.2f}" for x in meta["mu_e_values"])
        metadata_box(
            [
                ("Model", model_name),
                ("Feedback", feedback),
                ("Regime", hyst_regime),
                ("Fixed", f"d<sub>T</sub>={meta['expert_inertia_divisor']:.0f}, c<sub>pen</sub>={meta['c_pen']:.0f}"),
                ("Evidence strength", mu_vals),
                ("K", str(meta["cycle_length"])),
                ("N", f"{meta['n_runs']} runs"),
                ("T", f"{meta['n_trials']} trials"),
                ("Baseline trust", "Expert/Peers = 0.5/0.5"),
                ("Post-collapse trust", "Expert/Peers = 0.1/0.9"),
            ]
        )
    st.plotly_chart(hysteresis_trajectory_figure(traj, meta, model_name, feedback, hyst_regime), use_container_width=True)
    with st.expander("Steady-state summary values"):
        st.dataframe(summary)

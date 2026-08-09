import streamlit as st

from dashboard import live_sim, plotting

st.title("Live Simulator")
st.caption("Run a single simulation with new parameters. Results are not stored.")

st.markdown(
    "**How to read these plots:** solid line = mean across replications; shaded "
    "band = **95% CI** across replications. The boxed numbers report the "
    "**steady-state mean** (second half of trials, primary) and the "
    "**full-range mean** (all trials, secondary)."
)

if not live_sim._HAS_TRUSTBANDITS:
    st.warning(
        "The live simulator requires the `trustbandits` package, which is not "
        "installed in this deployment. Install it with "
        "`pip install -e ../trust-bandits-analysis`."
    )
    st.stop()

with st.sidebar:
    st.header("Parameters")
    mu_E = st.slider(plotting.mathify("Evidence strength (mu_E)"), 0.5, 0.95, 0.65, 0.025)
    c_pen = st.slider(plotting.mathify("Asymmetric penalty (c_pen)"), 1.0, 18.0, 6.0, 0.5)
    sigma_E = st.slider(plotting.mathify("Evidence noise (sigma_E)"), 0.0, 0.3, 0.1, 0.01)
    sigma_expert = st.slider(plotting.mathify("Expert noise (sigma_expert)"), 0.0, 0.5, 0.2, 0.01)
    sigma_peers_multiplier = st.slider(plotting.mathify("Peers noise multiplier (sigma_peers_multiplier)"), 1.0, 4.0, 2.0, 0.1)
    m_peers = st.slider(plotting.mathify("Number of peers (m_peers)"), 1, 10, 3)
    f_peers = st.slider(plotting.mathify("Peers sampling fraction (f_peers)"), 0.01, 0.5, 0.0625, 0.01)
    lr_base = st.slider(plotting.mathify("Learning rate (lr_base)"), 0.01, 0.5, 0.1, 0.01)
    tau = st.slider(plotting.mathify("Decision temperature (tau)"), 0.05, 1.0, 0.3, 0.05)
    w_init_expert = st.slider(plotting.mathify("Initial trust in Expert (w_init_expert)"), 0.0, 1.0, 0.5, 0.05)
    w_init_peers = st.slider(plotting.mathify("Initial trust in Peers (w_init_peers)"), 0.0, 1.0, 0.5, 0.05)
    feedback = st.selectbox("Feedback mode", ["full", "partial"])
    n_trials = st.slider("Trials", 20, 200, 50, 10)
    n_runs = st.slider("Replications", 1, 50, 1)
    run = st.button("Run simulation")

if run:
    with st.spinner("Running simulation..."):
        frames = []
        for i in range(n_runs):
            df = live_sim.run_live(
                n_trials=n_trials,
                mu_E=mu_E,
                c_pen=c_pen,
                sigma_E=sigma_E,
                sigma_expert=sigma_expert,
                sigma_peers_multiplier=sigma_peers_multiplier,
                m_peers=m_peers,
                f_peers=f_peers,
                lr_base=lr_base,
                tau=tau,
                w_init_expert=w_init_expert,
                w_init_peers=w_init_peers,
                feedback_mode=feedback,
                rng_seed=2025 + i,
            )
            df["run_id"] = i
            frames.append(df)
        import pandas as pd

        all_df = pd.concat(frames, ignore_index=True)
        agg = (
            all_df.groupby("trial")
            .agg(
                mean_p_expert=("p_expert", "mean"),
                sd_p_expert=("p_expert", "std"),
                mean_trust_expert=("trust_expert", "mean"),
                sd_trust_expert=("trust_expert", "std"),
                mean_trust_peers=("trust_peers", "mean"),
                sd_trust_peers=("trust_peers", "std"),
                mean_acc_expert=("correct_expert", "mean"),
                sd_acc_expert=("correct_expert", "std"),
                mean_acc_peers=("correct_peers", "mean"),
                sd_acc_peers=("correct_peers", "std"),
            )
            .reset_index()
        )
        agg["n_runs"] = n_runs

        # steady-state (second half of trials) and full-range means
        cutoff = n_trials // 2
        ss = all_df[all_df["trial"] > cutoff]
        stats = {
            "p_expert": {
                "steady": ss["p_expert"].mean(),
                "full": all_df["p_expert"].mean(),
            },
            "trust": {
                "steady": (ss["trust_expert"].mean(), ss["trust_peers"].mean()),
                "full": (all_df["trust_expert"].mean(), all_df["trust_peers"].mean()),
            },
            "accuracy": {
                "steady": (ss["correct_expert"].mean(), ss["correct_peers"].mean()),
                "full": (all_df["correct_expert"].mean(), all_df["correct_peers"].mean()),
            },
        }
    st.plotly_chart(
        plotting.trajectory_figure(
            agg, "p_expert", title=f"p(Expert) · μ<sub>E</sub>={mu_E} · c<sub>pen</sub>={c_pen} · N={n_runs}",
            stats=stats["p_expert"],
        ),
        use_container_width=True,
    )
    st.plotly_chart(
        plotting.trajectory_figure(
            agg, "trust", title="Trust over trials", stats=stats["trust"]
        ),
        use_container_width=True,
    )
    st.plotly_chart(
        plotting.trajectory_figure(
            agg, "accuracy", title="Accuracy over trials", stats=stats["accuracy"]
        ),
        use_container_width=True,
    )
else:
    st.info("Adjust the parameters and click **Run simulation**.")

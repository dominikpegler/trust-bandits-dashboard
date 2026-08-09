"""Run a single live simulation with arbitrary parameters.

Wraps trustbandits.simulation.run_single_simulation so the dashboard can run
one-off simulations with new parameter values without touching the database.
"""
from __future__ import annotations

import pandas as pd

try:
    from trustbandits.params import Study1SingleParams
    from trustbandits.simulation import run_single_simulation

    _HAS_TRUSTBANDITS = True
except Exception:  # pragma: no cover - live sim is optional
    _HAS_TRUSTBANDITS = False

DEFAULTS = dict(
    world_size=32,
    mu_E=0.65,
    sigma_E=0.1,
    sigma_expert=0.2,
    sigma_peers_multiplier=2.0,
    beta_expert=0.0,
    beta_peers=0.0,
    m_peers=3,
    f_expert=1.0,
    f_peers=0.0625,
    lr_base=0.1,
    c_pen=6.0,
    w_init_expert=0.5,
    w_init_peers=0.5,
    tau=0.3,
    peers_cost_weights=(0.5, 0.25),
    feedback_mode="full",
    clustering=0.0,
    rho_peers=0.0,
)


def run_live(
    n_trials: int = 50,
    rolling_window: int = 10,
    rng_seed: int = 2025,
    **overrides,
) -> pd.DataFrame:
    """Run one simulation with DEFAULTS overridden by `overrides`."""
    if not _HAS_TRUSTBANDITS:
        raise RuntimeError(
            "The live simulator requires the `trustbandits` package. "
            "Install it with `pip install -e ../trust-bandits-analysis`."
        )
    params = dict(DEFAULTS)
    params.update(overrides)
    cfg = Study1SingleParams(**params)
    return run_single_simulation(
        world_params=cfg.world_params(),
        src=cfg.source_params(),
        agent=cfg.agent_params(),
        n_trials=n_trials,
        rolling_window=rolling_window,
        rng_seed=rng_seed,
    )

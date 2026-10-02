"""Real CREST active-occupant-count transition-probability matrices
(TPMs), hourly-composed from the CREST Domestic Electricity Demand Model
1.0e's native 10-minute-resolution data.

Backs the ``markov_chain_crest`` generator
(:mod:`occupancy.core.occupancy_engine`). ``core/occupancy_engine.py``
itself stays CREST-agnostic — it only reads ``ctx.params["tpm_weekday"/
"tpm_weekend"]`` (see :func:`resolve_markov_chain_crest_params`, which
builds those params); this module is the only place that knows "CREST" and
"households" both.

**Scope**: real, source-attributed CREST data only covers the
active-occupant-count *transition* dynamics, for household sizes 1-5
(CREST's own modeled range — the source workbook's ``main`` sheet reads
"Specify the number of residents in the house: (Specify 1 to 5)"). It does
**not** cover the presence-vs-active split or ``n_asleep``, which continue
to come from this repo's own (non-CREST) ``home_probabilities``/
``active_probabilities``/``asleep_probabilities`` arrays exactly as in the
synthesized ``markov_chain`` generator — see
``households/household_profile.py``'s fallback wiring for households above
``MAX_CALIBRATED_SIZE``.

**Data provenance**: ``households/data/tpm_crest.json`` is derived from
``data/inputs/CREST_Domestic_electricity_demand_model_1.0e.xlsm``
(Richardson, Thomson, Infield — Loughborough University CREST; gitignored,
not committed — obtained directly via the paper's own public download
link, CC BY-NC-ND, no redistribution of the raw workbook). Extraction is
one-time and reproducible via ``scripts/extract_crest_tpm.py``; see that
script's docstring and ``households/data/tpm_crest.json``'s own
``_comment``/``_crest_source`` fields for the full attribution, matching
the precedent already set by ``households/data/equipment.json``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from occupancy.core.loader import load_json_resource

_PACKAGE = "occupancy.households"
_TPM_PATH = "data/tpm_crest.json"

# CREST's own modeled range: household sizes 1 through 5 residents. Larger
# households fall back to the synthesized `markov_chain` generator (see
# `household_profile.py`) rather than guessing/reusing the m=5 matrix.
MAX_CALIBRATED_SIZE = 5


@dataclass(frozen=True)
class CrestTpmTable:
    """Hourly-composed CREST transition-probability matrices for one
    household size."""

    num_persons: int
    # Shape (24, num_persons + 1, num_persons + 1), row-stochastic: each
    # weekday[hour] is the probability of transitioning FROM the
    # start-of-hour active-occupant count TO the start-of-next-hour count.
    weekday: np.ndarray
    weekend: np.ndarray


def compose_hourly_transition_matrix(
    ten_min_matrices: np.ndarray,
) -> np.ndarray:
    """Compose CREST's native 10-minute-resolution transition matrices
    into hourly ones.

    ``ten_min_matrices``: shape ``(144, n, n)``, row-stochastic 10-minute
    TPMs for one day-type (144 = 24 hours * 6 ten-minute periods/hour).
    Returns shape ``(24, n, n)``: ``P_hour[h] = P10[6h] @ P10[6h+1] @ ... @
    P10[6h+5]`` (0-indexed periods covering ``[h:00, h+1:00)``).

    This composition is exact for a discrete-time Markov chain (even a
    time-inhomogeneous one, which this is — the 10-minute transition
    probabilities vary by period) by the Chapman-Kolmogorov equation:
    right-multiplying a state distribution by ``P10[6h]``, then
    ``P10[6h+1]``, ... then ``P10[6h+5]`` marginalizes out the five
    unobserved intermediate 10-minute states, leaving exactly the true
    start-of-hour -> start-of-next-hour transition law -- *given* the
    chain is genuinely Markov at 10-minute granularity, which is CREST's
    own stated modeling assumption, not independently re-derived here.
    This does discard intra-hour timing detail, but this repo's engine
    only ever needs hour-boundary state (hourly resolution throughout).
    """
    ten_min_matrices = np.asarray(ten_min_matrices, dtype=float)
    if ten_min_matrices.shape[0] != 144:
        raise ValueError(
            "ten_min_matrices must have 144 periods (24h * 6 "
            f"per hour), got {ten_min_matrices.shape[0]}"
        )
    n = ten_min_matrices.shape[1]
    hourly = np.empty((24, n, n), dtype=float)
    for hour in range(24):
        composed = np.eye(n)
        for period in ten_min_matrices[hour * 6 : hour * 6 + 6]:
            composed = composed @ period
        hourly[hour] = composed
    return hourly


def load_crest_tpm(num_persons: int) -> CrestTpmTable:
    """Load ``households/data/tpm_crest.json``'s entry for ``num_persons``
    (1-5). Raises ``ValueError`` outside that range -- callers needing a
    fallback for larger households must check ``MAX_CALIBRATED_SIZE``
    themselves (see ``household_profile.py``)."""
    if not (1 <= num_persons <= MAX_CALIBRATED_SIZE):
        raise ValueError(
            f"No real CREST TPM data for num_persons={num_persons} -- "
            f"only sizes 1-{MAX_CALIBRATED_SIZE} are calibrated."
        )
    data: dict[str, Any] = load_json_resource(_PACKAGE, _TPM_PATH)
    entry = data[str(num_persons)]
    return CrestTpmTable(
        num_persons=num_persons,
        weekday=np.asarray(entry["weekday"], dtype=float),
        weekend=np.asarray(entry["weekend"], dtype=float),
    )


def resolve_markov_chain_crest_params(
    num_persons: int,
    generator_params: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a copy of ``generator_params`` with ``tpm_weekday``/
    ``tpm_weekend`` (each shape ``(24, num_persons + 1, num_persons + 1)``)
    populated from :func:`load_crest_tpm`. Only valid for ``num_persons``
    in ``1..MAX_CALIBRATED_SIZE``."""
    table = load_crest_tpm(num_persons)
    params = dict(generator_params or {})
    params["tpm_weekday"] = table.weekday
    params["tpm_weekend"] = table.weekend
    return params

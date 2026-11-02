"""Generate independent deterministic F39 analytical goldens (Python stdlib).

This is an external implementation from the Rust normal-normal code: Decimal
precision arithmetic and statistics.NormalDist quantiles. Synthetic values only.
No network, project/user data or executable notebook/kernel involvement.
"""

from __future__ import annotations

import json
from decimal import Decimal, localcontext
from pathlib import Path
from statistics import NormalDist


CASES = [
    {"observations": [2, 4, 6, 1, 3, 5], "prior_mean": 0, "prior_sd": 10, "observation_sd": 2, "credible_mass": 0.95},
    {"observations": [2], "prior_mean": 1, "prior_sd": 3, "observation_sd": 2, "credible_mass": 0.90},
    {"observations": list(range(1, 21)), "prior_mean": 7, "prior_sd": 4, "observation_sd": 5, "credible_mass": 0.99},
    {"observations": [-15, -4, -6, 10, 3], "prior_mean": -2, "prior_sd": 2, "observation_sd": 8, "credible_mass": 0.80},
]


def calculate(case: dict[str, object]) -> dict[str, object]:
    with localcontext() as context:
        context.prec = 55
        values = [Decimal(str(value)) for value in case["observations"]]  # type: ignore[union-attr]
        n = Decimal(len(values))
        mean = sum(values) / n
        prior_mean = Decimal(str(case["prior_mean"]))
        prior_sd = Decimal(str(case["prior_sd"]))
        observation_sd = Decimal(str(case["observation_sd"]))
        credible_mass = Decimal(str(case["credible_mass"]))
        prior_precision = Decimal(1) / (prior_sd * prior_sd)
        data_precision = n / (observation_sd * observation_sd)
        posterior_precision = prior_precision + data_precision
        posterior_mean = (prior_precision * prior_mean + data_precision * mean) / posterior_precision
        posterior_sd = (Decimal(1) / posterior_precision).sqrt()
        distribution = NormalDist(mu=float(posterior_mean), sigma=float(posterior_sd))
        tail = float((Decimal(1) - credible_mass) / 2)
        return {
            **case,
            "expected_sample_mean": float(mean),
            "expected_posterior_mean": float(posterior_mean),
            "expected_posterior_sd": float(posterior_sd),
            "expected_interval": [distribution.inv_cdf(tail), distribution.inv_cdf(1 - tail)],
        }


def main() -> None:
    destination = Path(__file__).resolve().parents[2] / "crates/researchweave-analysis/tests/fixtures/f39-bayes-normal-known-sd.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps({"format": "f39-normal-normal-independent-stdlib-v1", "cases": [calculate(case) for case in CASES]}, indent=2)
        + "\n", encoding="utf-8",
    )
    print(f"F39_STDLIB_ORACLE_WRITTEN={destination} cases={len(CASES)}")


if __name__ == "__main__":
    main()

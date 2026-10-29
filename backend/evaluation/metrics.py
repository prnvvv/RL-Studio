from __future__ import annotations

import math
from collections.abc import Iterable
from statistics import mean, median, pstdev

from .models import AcceptanceCriteria, EpisodeEvaluation

Z_95 = 1.959963984540054

METRIC_DEFINITIONS = {
    "valid_episode_count": "Episodes without a recorded infrastructure error.",
    "failed_episode_count": "Episodes excluded from performance metrics because an infrastructure error was recorded.",
    "success_rate": "Successful valid episodes / valid episodes.",
    "collision_rate": "Valid episodes with a collision / valid episodes.",
    "timeout_rate": "Valid episodes that timed out / valid episodes.",
    "mean_reward": "Arithmetic mean held-out episode reward over valid episodes.",
    "median_reward": "Median held-out episode reward over valid episodes.",
    "mean_episode_length": "Arithmetic mean length over valid episodes.",
    "median_episode_length": "Median length over valid episodes.",
    "success_rate_ci95": "Wilson score 95% interval for success rate over valid episodes.",
    "mean_reward_ci95": "Normal-approximation 95% interval for mean reward; null when fewer than two valid episodes.",
}


def _valid(episodes: Iterable[EpisodeEvaluation]) -> list[EpisodeEvaluation]:
    return [episode for episode in episodes if episode.error is None]


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def _wilson_interval(successes: int, total: int) -> dict[str, float] | None:
    if total <= 0:
        return None
    proportion = successes / total
    denominator = 1.0 + Z_95**2 / total
    centre = (proportion + Z_95**2 / (2.0 * total)) / denominator
    margin = (
        Z_95
        * math.sqrt(
            proportion * (1.0 - proportion) / total + Z_95**2 / (4.0 * total**2)
        )
        / denominator
    )
    return {
        "lower": _round(max(0.0, centre - margin)),
        "upper": _round(min(1.0, centre + margin)),
    }


def _mean_interval(values: list[float]) -> dict[str, float] | None:
    if len(values) < 2:
        return None
    standard_error = pstdev(values) / math.sqrt(len(values))
    average = mean(values)
    return {
        "lower": _round(average - Z_95 * standard_error),
        "upper": _round(average + Z_95 * standard_error),
    }


def summarize_episodes(episodes: list[EpisodeEvaluation]) -> dict:
    valid = _valid(episodes)
    valid_count = len(valid)
    success_count = sum(1 for episode in valid if episode.success)
    collision_count = sum(1 for episode in valid if episode.collision)
    timeout_count = sum(1 for episode in valid if episode.timed_out)
    rewards = [episode.reward for episode in valid]
    lengths = [episode.episode_length for episode in valid]

    return {
        "total_episode_count": len(episodes),
        "valid_episode_count": valid_count,
        "failed_episode_count": len(episodes) - valid_count,
        "success_rate": _round(success_count / valid_count) if valid_count else None,
        "collision_rate": _round(collision_count / valid_count) if valid_count else None,
        "timeout_rate": _round(timeout_count / valid_count) if valid_count else None,
        "mean_reward": _round(mean(rewards)) if rewards else None,
        "median_reward": _round(median(rewards)) if rewards else None,
        "mean_episode_length": _round(mean(lengths)) if lengths else None,
        "median_episode_length": _round(median(lengths)) if lengths else None,
        "confidence_intervals": {
            "success_rate": _wilson_interval(success_count, valid_count),
            "mean_reward": _mean_interval(rewards),
            "ci_method": {
                "success_rate": "wilson_score",
                "mean_reward": "normal_approximation",
            },
            "confidence_level": 0.95,
        },
    }


def _delta(
    recovered: dict, comparison: dict | None
) -> dict[str, float | None] | None:
    if comparison is None:
        return None
    result: dict[str, float | None] = {}
    for key in (
        "success_rate",
        "mean_reward",
        "median_reward",
        "mean_episode_length",
        "collision_rate",
        "timeout_rate",
    ):
        left = recovered.get(key)
        right = comparison.get(key)
        result[key] = (
            None if left is None or right is None else _round(left - right)
        )
    return result


def _seed_map(episodes: list[EpisodeEvaluation]) -> dict[int, EpisodeEvaluation] | None:
    result: dict[int, EpisodeEvaluation] = {}
    for episode in _valid(episodes):
        if episode.seed in result:
            return None
        result[episode.seed] = episode
    return result


def paired_comparison(
    baseline: list[EpisodeEvaluation], recovered: list[EpisodeEvaluation]
) -> dict | None:
    baseline_by_seed = _seed_map(baseline)
    recovered_by_seed = _seed_map(recovered)
    if baseline_by_seed is None or recovered_by_seed is None:
        return None
    if set(baseline_by_seed) != set(recovered_by_seed):
        return None
    differences = [
        recovered_by_seed[seed].reward - baseline_by_seed[seed].reward
        for seed in baseline_by_seed
    ]
    success_differences = [
        float(recovered_by_seed[seed].success)
        - float(baseline_by_seed[seed].success)
        for seed in baseline_by_seed
    ]
    return {
        "paired_episode_count": len(differences),
        "mean_reward_difference": _round(mean(differences)),
        "mean_success_rate_difference": _round(mean(success_differences)),
        "mean_reward_difference_ci95": _mean_interval(differences),
    }


def compare_groups(
    *,
    baseline: dict,
    recovered: dict,
    faulty: dict | None,
    baseline_episodes: list[EpisodeEvaluation],
    recovered_episodes: list[EpisodeEvaluation],
) -> dict:
    return {
        "recovered_minus_healthy_baseline": _delta(recovered, baseline),
        "recovered_minus_faulty": _delta(recovered, faulty),
        "paired_recovered_vs_healthy_baseline": paired_comparison(
            baseline_episodes, recovered_episodes
        ),
    }


def _check(
    name: str,
    threshold: object,
    observed: float | None,
    passed: bool,
) -> dict:
    return {
        "criterion": name,
        "threshold": threshold,
        "observed": _round(observed),
        "passed": passed,
        "evaluable": True,
    }


def _not_evaluable(name: str, threshold: object, reason: str) -> dict:
    return {
        "criterion": name,
        "threshold": threshold,
        "observed": None,
        "passed": False,
        "evaluable": False,
        "reason": reason,
    }


def evaluate_acceptance(
    *,
    criteria: AcceptanceCriteria,
    baseline: dict,
    faulty: dict | None,
    recovered: dict,
) -> dict:
    configured = criteria.model_dump(exclude_none=True)
    checks: list[dict] = []
    any_configured = any(
        value is not None and value is not False
        for value in configured.values()
    )

    if criteria.minimum_recovered_success_rate is not None:
        threshold = criteria.minimum_recovered_success_rate
        observed = recovered.get("success_rate")
        checks.append(
            _not_evaluable(
                "minimum_recovered_success_rate",
                threshold,
                "Recovered success rate is unavailable.",
            )
            if observed is None
            else _check(
                "minimum_recovered_success_rate", threshold, observed, observed >= threshold
            )
        )

    if criteria.minimum_success_rate_improvement_vs_faulty is not None:
        threshold = criteria.minimum_success_rate_improvement_vs_faulty
        recovered_rate = recovered.get("success_rate")
        faulty_rate = faulty.get("success_rate") if faulty else None
        if recovered_rate is None or faulty_rate is None:
            checks.append(
                _not_evaluable(
                    "minimum_success_rate_improvement_vs_faulty",
                    threshold,
                    "Faulty and recovered success rates are required.",
                )
            )
        else:
            observed = recovered_rate - faulty_rate
            checks.append(
                _check(
                    "minimum_success_rate_improvement_vs_faulty",
                    threshold,
                    observed,
                    observed >= threshold,
                )
            )

    if criteria.maximum_success_rate_regression_vs_healthy is not None:
        threshold = criteria.maximum_success_rate_regression_vs_healthy
        recovered_rate = recovered.get("success_rate")
        baseline_rate = baseline.get("success_rate")
        if recovered_rate is None or baseline_rate is None:
            checks.append(
                _not_evaluable(
                    "maximum_success_rate_regression_vs_healthy",
                    threshold,
                    "Healthy baseline and recovered success rates are required.",
                )
            )
        else:
            observed = baseline_rate - recovered_rate
            checks.append(
                _check(
                    "maximum_success_rate_regression_vs_healthy",
                    threshold,
                    observed,
                    observed <= threshold,
                )
            )

    if criteria.minimum_mean_reward_improvement_vs_faulty is not None:
        threshold = criteria.minimum_mean_reward_improvement_vs_faulty
        recovered_reward = recovered.get("mean_reward")
        faulty_reward = faulty.get("mean_reward") if faulty else None
        if recovered_reward is None or faulty_reward is None:
            checks.append(
                _not_evaluable(
                    "minimum_mean_reward_improvement_vs_faulty",
                    threshold,
                    "Faulty and recovered mean rewards are required.",
                )
            )
        else:
            observed = recovered_reward - faulty_reward
            checks.append(
                _check(
                    "minimum_mean_reward_improvement_vs_faulty",
                    threshold,
                    observed,
                    observed >= threshold,
                )
            )

    if criteria.maximum_mean_reward_regression_vs_healthy is not None:
        threshold = criteria.maximum_mean_reward_regression_vs_healthy
        recovered_reward = recovered.get("mean_reward")
        baseline_reward = baseline.get("mean_reward")
        if recovered_reward is None or baseline_reward is None:
            checks.append(
                _not_evaluable(
                    "maximum_mean_reward_regression_vs_healthy",
                    threshold,
                    "Healthy baseline and recovered mean rewards are required.",
                )
            )
        else:
            observed = baseline_reward - recovered_reward
            checks.append(
                _check(
                    "maximum_mean_reward_regression_vs_healthy",
                    threshold,
                    observed,
                    observed <= threshold,
                )
            )

    if criteria.maximum_collision_rate is not None:
        threshold = criteria.maximum_collision_rate
        observed = recovered.get("collision_rate")
        checks.append(
            _not_evaluable(
                "maximum_collision_rate",
                threshold,
                "Recovered collision rate is unavailable.",
            )
            if observed is None
            else _check("maximum_collision_rate", threshold, observed, observed <= threshold)
        )

    if criteria.maximum_timeout_rate is not None:
        threshold = criteria.maximum_timeout_rate
        observed = recovered.get("timeout_rate")
        checks.append(
            _not_evaluable(
                "maximum_timeout_rate",
                threshold,
                "Recovered timeout rate is unavailable.",
            )
            if observed is None
            else _check("maximum_timeout_rate", threshold, observed, observed <= threshold)
        )

    if criteria.minimum_valid_episodes_per_group is not None:
        threshold = criteria.minimum_valid_episodes_per_group
        groups = {"healthy_baseline": baseline, "recovered": recovered}
        if faulty is not None:
            groups["faulty_baseline"] = faulty
        for name, summary in groups.items():
            observed = summary.get("valid_episode_count")
            if observed is None:
                checks.append(
                    _not_evaluable(
                        f"minimum_valid_episodes_per_group:{name}",
                        threshold,
                        f"{name} valid episode count is unavailable.",
                    )
                )
            else:
                checks.append(
                    _check(
                        f"minimum_valid_episodes_per_group:{name}",
                        threshold,
                        float(observed),
                        observed >= threshold,
                    )
                )

    if criteria.require_no_episode_errors:
        groups = {"healthy_baseline": baseline, "recovered": recovered}
        if faulty is not None:
            groups["faulty_baseline"] = faulty
        for name, summary in groups.items():
            observed = summary.get("failed_episode_count")
            checks.append(
                _check(
                    f"no_episode_errors:{name}",
                    0,
                    float(observed or 0),
                    observed == 0,
                )
            )

    if not any_configured:
        return {
            "status": "inconclusive",
            "reason": (
                "No acceptance criteria were configured. Metrics are descriptive "
                "and recovery is not verified."
            ),
            "checks": [],
            "configured": False,
        }

    failed = any(
        check["evaluable"] and not check["passed"] for check in checks
    )
    unevaluable = any(not check["evaluable"] for check in checks)
    if failed:
        status = "failed"
        reason = "At least one configured acceptance criterion was not met."
    elif unevaluable:
        status = "inconclusive"
        reason = "At least one configured acceptance criterion could not be evaluated."
    else:
        status = "passed"
        reason = "All configured acceptance criteria were met."
    return {
        "status": status,
        "reason": reason,
        "checks": checks,
        "configured": True,
    }

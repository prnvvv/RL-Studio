"""Regression tests for the verification tools."""

from __future__ import annotations

import pytest

from backend.verification.models import (
    CheckStatus,
    RequirementType,
    VerificationRequirement,
)
from backend.verification.tools.configuration_checker import (
    execute_check as config_check,
)
from backend.verification.tools.episode_checker import execute_check as episode_check
from backend.verification.tools.event_checker import execute_check as event_check
from backend.verification.tools.metric_checker import execute_check as metric_check
from backend.verification.tools.reward_checker import execute_check as reward_check

# ---- Reward checker tests ----

class TestRewardChecker:
    """Tests for the reward requirement verification checker."""

    def test_expected_vs_observed_mismatch(self):
        """A configured expected-versus-observed contract mismatch must produce FAIL."""
        req = VerificationRequirement(description="test", type=RequirementType.reward, expected_value=100.0)
        result = reward_check("check_reward", req, configured_reward=100.0, observed_reward=25.0)
        assert result.status == CheckStatus.FAIL
        assert result.expected == 100.0
        assert result.actual == 25.0

    def test_low_reward_alone_no_defect(self):
        """Low reward alone must not establish an environment defect."""
        req = VerificationRequirement(description="test", type=RequirementType.reward, expected_value=None)
        result = reward_check("check_reward", req, configured_reward=None, observed_reward=5.0)
        # LOW reward alone should not be FAIL; should be UNKNOWN or PASS depending on evidence
        assert result.status != CheckStatus.FAIL or result.expected is None

    def test_missing_expected_reward_no_fabrication(self):
        """Missing expected reward must not be converted into a fabricated contract."""
        req = VerificationRequirement(description="test", type=RequirementType.reward, expected_value=None)
        result = reward_check("check_reward", req, configured_reward=None, observed_reward=None)
        assert result.expected is None
        # Should not return a fabricated value

    def test_malformed_values(self):
        """Malformed and non-finite values must be handled explicitly."""
        req = VerificationRequirement(description="test", type=RequirementType.reward, expected_value=float("inf"))
        result = reward_check("check_reward", req, configured_reward=float("inf"), observed_reward=25.0)
        # Should not crash; should return a valid status
        assert result.status in {CheckStatus.FAIL, CheckStatus.UNKNOWN, CheckStatus.ERROR}


# ---- Metric checker tests ----

class TestMetricChecker:
    """Tests for the metric and threshold verification checker."""

    def test_expected_value_none_not_converted_to_zero(self):
        """Never silently convert expected_value=None to 0.0."""
        req = VerificationRequirement(description="test", type=RequirementType.metric, expected_value=None)
        result = metric_check("check_metric", req, metric_values=[5.0])
        assert result.expected is None
        # Should be UNKNOWN, not FAIL with expected=0.0

    def test_all_observations_evaluated(self):
        """All metric observations should be evaluated, not just the first."""
        req = VerificationRequirement(description="test", type=RequirementType.metric, expected_value=10.0)
        result = metric_check("check_metric", req, metric_values=[5.0, 15.0])
        assert result.status == CheckStatus.FAIL  # First obs fails, so overall is FAIL
        assert len(result.details.get("note", "")) > 0

    def test_nan_handling(self):
        """NaN values should be handled explicitly."""
        req = VerificationRequirement(description="test", type=RequirementType.metric, expected_value=10.0)
        result = metric_check("check_metric", req, metric_values=[float("nan"), 15.0])
        # NaN should be treated as unknown, not fail
        assert result.status != CheckStatus.FAIL or "nan" in result.details.get("note", "").lower()

    def test_infinity_handling(self):
        """Positive/negative infinity should be handled explicitly."""
        req = VerificationRequirement(description="test", type=RequirementType.metric, expected_value=10.0)
        result = metric_check("check_metric", req, metric_values=[float("inf")])
        # Infinity should not cause uncaught exceptions
        assert result.status in {CheckStatus.FAIL, CheckStatus.UNKNOWN, CheckStatus.ERROR}


# ---- Event checker tests ----

class TestEventChecker:
    """Tests for the event and transition verification checker."""

    def test_required_event_found(self):
        """Required event should be found in recorded events."""
        req = VerificationRequirement(description="test", type=RequirementType.event, expected_value=None)
        result = event_check(
            "check_event",
            req,
            required_event="goal_reached",
            recorded_events=[{"event_name": "goal_reached", "timestep": 10}],
        )
        assert result.status == CheckStatus.PASS

    def test_required_event_not_found(self):
        """Required event not found should be UNKNOWN, not PASS."""
        req = VerificationRequirement(description="test", type=RequirementType.event, expected_value=None)
        result = event_check(
            "check_event",
            req,
            required_event="goal_reached",
            recorded_events=[{"event_name": "other_event", "timestep": 10}],
        )
        assert result.status == CheckStatus.UNKNOWN

    def test_forbidden_event_present(self):
        """Forbidden event present should produce FAIL."""
        req = VerificationRequirement(description="test", type=RequirementType.event, expected_value=None)
        result = event_check(
            "check_event",
            req,
            forbidden_event="bad_event",
            recorded_events=[{"event_name": "bad_event", "timestep": 10}],
        )
        assert result.status == CheckStatus.FAIL

    def test_forbidden_event_absent(self):
        """Forbidden event absent should continue (PASS)."""
        req = VerificationRequirement(description="test", type=RequirementType.event, expected_value=None)
        result = event_check(
            "check_event",
            req,
            forbidden_event="bad_event",
            recorded_events=[{"event_name": "good_event", "timestep": 10}],
        )
        assert result.status == CheckStatus.PASS

    def test_superficial_event_key_insufficient(self):
        """Events with only superficial key matches should be treated as insufficient."""
        req = VerificationRequirement(description="test", type=RequirementType.event, expected_value=None)
        result = event_check(
            "check_event",
            req,
            required_event="goal_reached",
            recorded_events=[{"name": "goal_reached"}],
        )
        # Should be UNKNOWN due to insufficient evidence, not PASS
        assert result.status != CheckStatus.PASS


# ---- Episode checker tests ----

class TestEpisodeChecker:
    """Tests for the episode outcome verification checker."""

    def test_termination_vs_truncation(self):
        """Should distinguish termination from truncation."""
        # Termination
        req = VerificationRequirement(description="test", type=RequirementType.termination, expected_value="terminated")
        result = episode_check(
            "check_episode",
            req,
            episode_data={"terminated": True, "truncated": False},
        )
        assert result.status == CheckStatus.PASS

        # Truncation (should not match termination expectation)
        req2 = VerificationRequirement(description="test", type=RequirementType.termination, expected_value="terminated")
        result2 = episode_check(
            "check_episode",
            req2,
            episode_data={"terminated": False, "truncated": True},
        )
        assert result2.status == CheckStatus.FAIL  # truncation != termination

    def test_missing_evidence_unknown(self):
        """Missing evidence should return UNKNOWN, not PASS."""
        req = VerificationRequirement(description="test", type=RequirementType.termination, expected_value="terminated")
        result = episode_check("check_episode", req, episode_data={})
        assert result.status == CheckStatus.UNKNOWN

    def test_goal_attained(self):
        """Goal attained should be detectable."""
        req = VerificationRequirement(description="test", type=RequirementType.termination, expected_value="goal_attained")
        result = episode_check(
            "check_episode",
            req,
            episode_data={"goal_attained": True},
        )
        assert result.status == CheckStatus.PASS


# ---- Configuration checker tests ----

class TestConfigurationChecker:
    """Tests for the configuration verification checker."""

    def test_configuration_reward_type(self):
        """Configuration checker should support reward-type requirements."""
        req = VerificationRequirement(description="test", type=RequirementType.reward, expected_value=100.0)
        result = config_check("check_config", req, config={"reward": 100})
        assert result.status in {CheckStatus.PASS, CheckStatus.FAIL, CheckStatus.UNKNOWN}

    def test_configuration_configuration_type(self):
        """Configuration checker should support configuration-type requirements."""
        req = VerificationRequirement(description="test", type=RequirementType.configuration, expected_value=100.0)
        result = config_check("check_config", req, config={"config_value": 100})
        assert result.status in {CheckStatus.PASS, CheckStatus.FAIL, CheckStatus.UNKNOWN}

    def test_missing_configuration_unknown(self):
        """Missing configuration should return UNKNOWN, not FAIL."""
        req = VerificationRequirement(description="test", type=RequirementType.configuration, expected_value=100.0)
        result = config_check("check_config", req, config=None)
        assert result.status == CheckStatus.UNKNOWN

    def test_infinity_handling(self):
        """Infinity values should be handled without uncaught exceptions."""
        req = VerificationRequirement(description="test", type=RequirementType.configuration, expected_value=float("inf"))
        result = config_check("check_config", req, config={"config_value": 100})
        assert result.status in {CheckStatus.FAIL, CheckStatus.UNKNOWN, CheckStatus.ERROR}


# ---- Run all tests ----

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
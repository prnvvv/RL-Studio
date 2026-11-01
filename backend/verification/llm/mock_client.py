"""Deterministic offline investigator used instead of a live Meta model.

This module exists so that the *real* LangGraph workflow, the real result
validator and the real report builder can be exercised end to end without
credentials, without network access, and without spending credits.

It is an explicit offline stub:

* ``provider`` is ``"offline_mock"`` and ``live_request`` is ``False`` in its
  metadata, so no caller can mistake its output for a Meta Model API response.
* ``root_cause_status`` is always ``"unresolved"`` and ``confidence`` is always
  ``None``: the stub never invents a confirmed cause or a calibrated score.
* Every fact, hypothesis and recommendation is derived from the supplied
  evidence bundle; when the bundle is empty the result says so.
* Output is a pure function of the request (no randomness, no clock, no I/O),
  so tests are reproducible.

Only the external provider boundary is replaced.  Nothing here validates,
grades, or overrides a deterministic check result.
"""

from __future__ import annotations

import copy
from typing import Any

#: Stable provider and model identifiers reported in metadata.
PROVIDER_NAME = "offline_mock"
MODEL_NAME = "offline-deterministic-v1"

#: Statuses that represent a deterministic contract violation.
_VIOLATION_STATUSES = frozenset({"fail", "violation"})


def _as_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _string_refs(value: Any) -> list[str]:
    refs: list[str] = []
    for item in _as_list(value):
        if isinstance(item, str) and item and item not in refs:
            refs.append(item)
    return refs


def _status_of(result: dict[str, Any]) -> str:
    status = result.get("status")
    return status if isinstance(status, str) else "unknown"


class OfflineMockMetaClient:
    """Deterministic, offline implementation of ``MetaAIProvider.investigate``.

    Args:
        provider_name: Override for the reported provider label (default
            ``"offline_mock"``).  Useful only to distinguish several stubs in a
            test; it never makes the client look like a live provider.
    """

    def __init__(self, provider_name: str = PROVIDER_NAME) -> None:
        self.provider = provider_name
        self.model = MODEL_NAME
        #: Request summaries for assertions.  Prompts/evidence bodies are not
        #: retained so that a test cannot accidentally treat stored input as
        #: model output.
        self.calls: list[dict[str, Any]] = []

    # -- helpers ---------------------------------------------------------

    def _record_call(self, request: dict[str, Any]) -> None:
        evidence = _as_mapping(request.get("evidence"))
        self.calls.append(
            {
                "prompt_version": request.get("prompt_version"),
                "incident_requirement_ids": _string_refs(
                    request.get("incident_requirement_ids")
                ),
                "has_evidence": bool(evidence),
                "missing_evidence": _string_refs(evidence.get("missing_evidence")),
            }
        )

    @staticmethod
    def _observed_facts(evidence: dict[str, Any]) -> list[dict[str, Any]]:
        facts: list[dict[str, Any]] = []
        for fact in _as_list(evidence.get("observed_facts")):
            entry = _as_mapping(fact)
            label = entry.get("fact")
            if not isinstance(label, str) or not label:
                continue
            item: dict[str, Any] = {"fact": label, "value": entry.get("value")}
            refs = _string_refs(entry.get("evidence_refs"))
            if refs:
                item["evidence_refs"] = refs
            facts.append(item)

        for result in _as_list(evidence.get("check_results")):
            entry = _as_mapping(result)
            requirement_id = entry.get("requirement_id")
            if not isinstance(requirement_id, str) or not requirement_id:
                continue
            item = {
                "fact": "requirement_check_result",
                "requirement_id": requirement_id,
                "status": _status_of(entry),
                "expected": entry.get("expected"),
                "actual": entry.get("actual"),
            }
            refs = _string_refs(entry.get("evidence_refs"))
            if refs:
                item["evidence_refs"] = refs
            facts.append(item)
        return facts

    @staticmethod
    def _supporting_evidence(evidence: dict[str, Any]) -> list[dict[str, Any]]:
        supporting: list[dict[str, Any]] = []
        for result in _as_list(evidence.get("check_results")):
            entry = _as_mapping(result)
            refs = _string_refs(entry.get("evidence_refs"))
            if not refs:
                continue
            supporting.append(
                {
                    "requirement_id": entry.get("requirement_id"),
                    "status": _status_of(entry),
                    "evidence_refs": refs,
                    "reason": "evidence referenced by the deterministic check result",
                }
            )
        return supporting

    @staticmethod
    def _candidate_causes(evidence: dict[str, Any]) -> list[dict[str, Any]]:
        """Derive *hypotheses* from non-passing check results.

        A mismatched value is a difference, not a proven cause; each entry is
        therefore labelled ``hypothesis`` and carries ``root_cause_status``
        ``unresolved``.
        """
        candidates: list[dict[str, Any]] = []
        for result in _as_list(evidence.get("check_results")):
            entry = _as_mapping(result)
            status = _status_of(entry)
            requirement_id = entry.get("requirement_id")
            if status == "pass" or not isinstance(requirement_id, str):
                continue
            expected = entry.get("expected")
            actual = entry.get("actual")
            if status in _VIOLATION_STATUSES:
                hypothesis = (
                    f"Requirement {requirement_id} is violated: the recorded value "
                    f"({actual!r}) differs from the expected value ({expected!r}). "
                    "The cause of the difference is not established by this evidence."
                )
            else:
                hypothesis = (
                    f"Requirement {requirement_id} could not be evaluated "
                    f"(status={status}); no cause can be inferred without more evidence."
                )
            candidates.append(
                {
                    "hypothesis": hypothesis,
                    "requirement_id": requirement_id,
                    "root_cause_status": "unresolved",
                    "confidence": None,
                    "evidence_refs": _string_refs(entry.get("evidence_refs")),
                }
            )
        return candidates

    @staticmethod
    def _recommended_tests(evidence: dict[str, Any]) -> list[str]:
        tests: list[str] = []
        for item in _string_refs(evidence.get("missing_evidence")):
            tests.append(f"Collect the missing evidence: {item}.")
        for result in _as_list(evidence.get("check_results")):
            entry = _as_mapping(result)
            requirement_id = entry.get("requirement_id")
            status = _status_of(entry)
            if not isinstance(requirement_id, str):
                continue
            if status in _VIOLATION_STATUSES:
                tests.append(
                    f"Re-run the episode with the configured expectation for "
                    f"{requirement_id} and compare the recorded value against it."
                )
            elif status not in {"pass"}:
                tests.append(
                    f"Provide complete evidence for {requirement_id} before "
                    "re-evaluating the requirement."
                )
        # Stable, de-duplicated order.
        return list(dict.fromkeys(tests))

    # -- public API ------------------------------------------------------

    def investigate(self, request: dict[str, Any]) -> dict[str, Any]:
        """Return a deterministic advisory payload derived from *request*.

        Raises:
            TypeError: If *request* is not a mapping.  (A programming error, not
                a provider failure.)
        """
        if not isinstance(request, dict):
            raise TypeError("investigation request must be a dictionary")

        self._record_call(request)
        evidence = _as_mapping(request.get("evidence"))
        missing = _string_refs(evidence.get("missing_evidence"))
        environment_version = evidence.get("environment_version")
        run_identifier = evidence.get("run_identifier")

        observed_facts = self._observed_facts(evidence)
        candidate_causes = self._candidate_causes(evidence)
        supporting_evidence = self._supporting_evidence(evidence)
        recommended_tests = self._recommended_tests(evidence)

        violated = [
            _as_mapping(result).get("requirement_id")
            for result in _as_list(evidence.get("check_results"))
            if _status_of(_as_mapping(result)) in _VIOLATION_STATUSES
        ]
        violated_ids = [item for item in violated if isinstance(item, str)]

        summary_parts = [
            f"Offline deterministic analysis of {len(observed_facts)} observed fact(s).",
        ]
        if violated_ids:
            summary_parts.append(
                f"{len(violated_ids)} requirement(s) violated: {', '.join(violated_ids)}."
            )
        else:
            summary_parts.append(
                "No deterministic violation is present in this bundle."
            )
        if missing:
            summary_parts.append(
                f"{len(missing)} item(s) of evidence are missing, so causes remain unresolved."
            )
        summary = " ".join(summary_parts)

        limitations = [
            (
                "Offline deterministic investigator: no Meta Model API request was made, "
                "so this text is not a model response."
            ),
            (
                "Candidate causes are hypotheses derived from the supplied evidence bundle; "
                "they are not confirmed root causes."
            ),
        ]
        for item in missing:
            limitations.append(f"Missing evidence: {item}.")
        if not evidence:
            limitations.append(
                "No evidence bundle was supplied; nothing could be analysed."
            )
        if not supporting_evidence:
            limitations.append(
                "No evidence references were supplied, so no recommendation is "
                "traceable to raw evidence."
            )

        return {
            "summary": summary,
            "observed_facts": observed_facts,
            "candidate_causes": candidate_causes,
            "supporting_evidence": supporting_evidence,
            "contradicting_evidence": [],
            "confidence": None,
            "root_cause_status": "unresolved",
            "recommended_tests": recommended_tests,
            "limitations": limitations,
            "run_identifier": run_identifier,
            "environment_version": environment_version,
            "incident_requirement_ids": _string_refs(
                request.get("incident_requirement_ids")
            ),
            "_metadata": {
                "provider": self.provider,
                "model": self.model,
                "offline": True,
                "live_request": False,
                "prompt_version": request.get("prompt_version"),
                "request_keys": sorted(str(key) for key in request),
            },
        }

    def invoke(
        self,
        model: str,
        messages: list[dict[str, Any]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Transport-compatible shim that never performs I/O.

        The content is a JSON object built from the request described by
        *messages*; it is intentionally minimal so that no test can rely on the
        stub pretending to be a live model.
        """
        del temperature, max_tokens, response_format, kwargs
        self.calls.append({"invoke_model": model, "message_count": len(messages or [])})
        payload = {
            "summary": "Offline stub transport: no model was called.",
            "observed_facts": [],
            "candidate_causes": [],
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "confidence": None,
            "root_cause_status": "unresolved",
            "recommended_tests": [],
            "limitations": [
                "Offline deterministic stub; no Meta Model API request was made."
            ],
            "_metadata": {
                "provider": self.provider,
                "model": model or self.model,
                "offline": True,
                "live_request": False,
            },
        }
        raw = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": __import__("json").dumps(payload, sort_keys=True),
                    },
                    "finish_reason": "stop",
                }
            ],
            "model": model or self.model,
        }
        return raw, {}

    def snapshot(self) -> list[dict[str, Any]]:
        """Return a copy of the recorded call summaries."""
        return copy.deepcopy(self.calls)


#: Convenience factory so callers do not need to import the class.
def build_offline_client(provider_name: str = PROVIDER_NAME) -> OfflineMockMetaClient:
    """Return a new offline client."""
    return OfflineMockMetaClient(provider_name=provider_name)


__all__ = [
    "MODEL_NAME",
    "PROVIDER_NAME",
    "OfflineMockMetaClient",
    "build_offline_client",
]

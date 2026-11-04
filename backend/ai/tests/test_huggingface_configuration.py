"""Configuration tests for the hosted Qwen vision and Mask2Former segmentation integrations.

These validate settings and the diagnostics vocabulary. Passing them proves the configuration is *consistent*; it is not
evidence that either hosted API works (that is what ``test_live_hosted_ai.py`` is for).
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from backend.ai import diagnostics as d
from backend.ai.errors import AIAuthError, AIRateLimitError
from backend.ai.service import AIService
from backend.ai.settings import AISettings
from backend.ai.tests.hf_support import SECRET

ROOT = Path(__file__).resolve().parents[3]
GOOD: dict[str, str] = {
    "GROQ_API_KEY": "gsk_unused", "HF_TOKEN": SECRET, "VISION_PROVIDER": "huggingface",
    "VISION_MODEL": d.EXPECTED_QWEN_MODEL, "HF_INFERENCE_BASE_URL": d.EXPECTED_ROUTER_URL,
    "HF_INFERENCE_PROVIDER": "hf-inference", "HF_SEGMENTATION_MODEL": d.EXPECTED_SEGMENTATION_MODEL,
}


def failing(env: dict[str, str]) -> set[str]:
    return {c.name for c in d.config_checks(AISettings.from_env(env)) if not c.ok}


def test_a_complete_configuration_passes_every_check() -> None:
    assert failing(GOOD) == set()


@pytest.mark.parametrize(("change", "expected"), [
    ({"HF_TOKEN": ""}, "HF_TOKEN present and not a placeholder"),
    ({"HF_TOKEN": "REPLACE_WITH_HF_TOKEN"}, "HF_TOKEN present and not a placeholder"),
    ({"HF_TOKEN": "YOUR_TOKEN_HERE"}, "HF_TOKEN present and not a placeholder"),
    ({"VISION_MODEL": ""}, "VISION_MODEL is configured"),
    ({"VISION_MODEL": "Qwen/Qwen2.5-VL-3B-Instruct"}, "VISION_MODEL carries the :featherless-ai provider suffix"),
    ({"VISION_MODEL": "Qwen/Qwen2.5-VL-3B-Instruct:together"}, "VISION_MODEL carries the :featherless-ai provider suffix"),
    ({"VISION_MODEL": "Qwen/Qwen2.5-VL-7B-Instruct:featherless-ai"}, "VISION_MODEL is the Qwen2.5-VL-3B model"),
    ({"VISION_PROVIDER": "groq"}, "VISION_PROVIDER is huggingface"),
    ({"HF_INFERENCE_BASE_URL": "https://api.groq.com/openai/v1"}, "HF_INFERENCE_BASE_URL is the Hugging Face router"),
    ({"HF_SEGMENTATION_MODEL": ""}, "HF_SEGMENTATION_MODEL is Mask2Former panoptic"),
    ({"HF_SEGMENTATION_MODEL": "facebook/sam-vit-base"}, "HF_SEGMENTATION_MODEL is Mask2Former panoptic"),
    ({"HF_INFERENCE_PROVIDER": "featherless-ai"}, "HF_INFERENCE_PROVIDER is hf-inference"),
])
def test_each_misconfiguration_is_reported_by_name(change: dict[str, str], expected: str) -> None:
    assert expected in failing({**GOOD, **change})


def test_provider_names_and_model_ids_are_not_confused() -> None:
    """The Qwen provider is a suffix of the model id; hf-inference is the segmentation provider."""
    s = AISettings.from_env(GOOD)
    assert s.vision_model.split(":")[1] == "featherless-ai" and s.hf_inference_provider == "hf-inference"
    assert ":" not in s.hf_segmentation_model and "featherless" not in s.hf_segmentation_model
    swapped = failing({**GOOD, "VISION_MODEL": d.EXPECTED_SEGMENTATION_MODEL, "HF_SEGMENTATION_MODEL": d.EXPECTED_QWEN_MODEL})
    assert "VISION_MODEL is the Qwen2.5-VL-3B model" in swapped and "HF_SEGMENTATION_MODEL is Mask2Former panoptic" in swapped


def test_an_unset_provider_defaults_to_hf_inference_but_models_are_never_defaulted() -> None:
    s = AISettings.from_env({"HF_TOKEN": SECRET})
    assert s.hf_inference_provider == "hf-inference"
    assert s.vision_model == "" and s.hf_segmentation_model == ""  # disabled until configured, never guessed


def test_a_placeholder_token_means_the_hugging_face_features_are_unconfigured() -> None:
    service = AIService(AISettings.from_env({**GOOD, "HF_TOKEN": "REPLACE_WITH_HF_TOKEN"}))
    tasks = service.status()["tasks"]
    assert tasks["visual_investigation"]["state"] == "unconfigured"
    assert tasks["visual_segmentation"]["state"] == "unconfigured"
    assert d.probe_vision(service.settings).state == d.NOT_CONFIGURED
    assert d.probe_segmentation(service.settings).state == d.NOT_CONFIGURED


def test_status_reports_names_and_booleans_but_never_a_secret() -> None:
    status = AIService(AISettings.from_env({**GOOD, "HF_VISION_API_KEY": "hf_dedicated_secret"})).status()
    blob = repr(status)
    assert SECRET not in blob and "hf_dedicated_secret" not in blob
    assert status["tasks"]["visual_investigation"]["api_key_source"] == "dedicated"
    assert status["config"]["huggingface_configured"] is True


# ---- diagnostics vocabulary ------------------------------------------------------------------------------------------
class FakeApi:
    def __init__(self, mappings: list[Any] | Exception) -> None:
        self.mappings = mappings

    def __call__(self, token: str | None = None) -> FakeApi:
        return self

    def model_info(self, model_id: str, expand: list[str] | None = None) -> Any:
        if isinstance(self.mappings, Exception):
            raise self.mappings
        return SimpleNamespace(inference_provider_mapping=self.mappings)


def mapping(provider: str, status: str) -> Any:
    return SimpleNamespace(provider=provider, status=status)


def listing(monkeypatch: pytest.MonkeyPatch, api: FakeApi, provider: str = "hf-inference") -> tuple[str, str]:
    import huggingface_hub

    monkeypatch.setattr(huggingface_hub, "HfApi", api)
    return d.model_listing(SECRET, "facebook/mask2former-swin-large-coco-panoptic", provider)


def test_model_listing_distinguishes_available_not_live_unlisted_and_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    from huggingface_hub.errors import HfHubHTTPError

    assert listing(monkeypatch, FakeApi([mapping("hf-inference", "live")]))[0] == d.MODEL_AVAILABLE
    assert listing(monkeypatch, FakeApi([mapping("hf-inference", "error")]))[0] == d.PROVIDER_UNAVAILABLE
    assert listing(monkeypatch, FakeApi([mapping("together", "live")]))[0] == d.PROVIDER_UNAVAILABLE
    assert listing(monkeypatch, FakeApi([]))[0] == d.PROVIDER_UNAVAILABLE
    import httpx2

    def hub(status: int) -> HfHubHTTPError:
        req = httpx2.Request("GET", "https://huggingface.co/api/models/x")
        return HfHubHTTPError("x", response=httpx2.Response(status, json={}, request=req))

    assert listing(monkeypatch, FakeApi(hub(401)))[0] == d.AUTHENTICATION_FAILED
    assert listing(monkeypatch, FakeApi(hub(429)))[0] == d.RATE_LIMITED
    assert listing(monkeypatch, FakeApi(hub(404)))[0] == d.PROVIDER_UNAVAILABLE
    assert listing(monkeypatch, FakeApi(OSError("offline")))[0] == d.PROVIDER_UNAVAILABLE


def test_a_listed_model_is_not_reported_as_a_successful_inference(monkeypatch: pytest.MonkeyPatch) -> None:
    """MODEL_AVAILABLE is metadata only; INFERENCE_SUCCESSFUL requires a real call to return usable output."""
    monkeypatch.setattr(d, "model_listing", lambda *a, **k: (d.MODEL_AVAILABLE, "listed"))
    settings = AISettings.from_env(GOOD)

    def refuse(self: AIService, *a: Any, **k: Any) -> Any:
        raise AIAuthError("huggingface rejected the configured credentials")

    monkeypatch.setattr(AIService, "analyze_image", refuse)
    probe = d.probe_vision(settings)
    assert probe.state == d.AUTHENTICATION_FAILED and d.INFERENCE_SUCCESSFUL not in probe.reached
    assert d.MODEL_AVAILABLE in probe.reached

    def limited(self: AIService, *a: Any, **k: Any) -> Any:
        raise AIRateLimitError("huggingface rate limit or quota reached")

    monkeypatch.setattr(AIService, "segment_image", limited)
    assert d.probe_segmentation(settings).state == d.RATE_LIMITED

    monkeypatch.setattr(AIService, "segment_image", lambda self, *a, **k: {"masks": []})
    empty = d.probe_segmentation(settings)
    assert empty.state == d.MODEL_AVAILABLE and d.INFERENCE_SUCCESSFUL not in empty.reached


def test_a_402_is_reported_as_quota_exceeded_not_as_an_outage_or_bad_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.ai.errors import AIQuotaError

    monkeypatch.setattr(d, "model_listing", lambda *a, **k: (d.MODEL_AVAILABLE, "listed"))
    settings = AISettings.from_env(GOOD)
    refuse = lambda self, *a, **k: (_ for _ in ()).throw(AIQuotaError("credits exhausted"))
    monkeypatch.setattr(AIService, "analyze_image", refuse)
    monkeypatch.setattr(AIService, "segment_image", refuse)
    for probe in (d.probe_vision(settings), d.probe_segmentation(settings)):
        assert probe.state == d.QUOTA_EXCEEDED
        assert d.MODEL_AVAILABLE in probe.reached and d.INFERENCE_SUCCESSFUL not in probe.reached


def test_the_probe_image_is_generated_locally_and_valid() -> None:
    from backend.ai.imaging import inspect_image

    info = inspect_image(d.probe_image(), 1_000_000)
    assert info.mime == "image/png" and (info.width, info.height) == (160, 160)


# ---- no local inference ------------------------------------------------------------------------------------------------
def test_importing_the_hosted_integrations_loads_no_local_inference_library() -> None:
    code = (
        f"import sys; sys.path.insert(0, {str(ROOT)!r})\n"
        "import backend.ai.service, backend.ai.vision, backend.ai.segmentation, backend.ai.diagnostics\n"
        "from backend.ai.service import AIService\nfrom backend.ai.settings import AISettings\n"
        "s = AIService(AISettings.from_env({'HF_TOKEN':'hf_x','VISION_MODEL':'Qwen/Qwen2.5-VL-3B-Instruct:featherless-ai',"
        "'HF_SEGMENTATION_MODEL':'facebook/mask2former-swin-large-coco-panoptic'}))\n"
        "s.vision_client(); s.segmentation_client()\n"
        "print(sorted(m for m in ('torch','torchvision','transformers') if m in sys.modules))\n"
    )
    out = subprocess.run([sys.executable, "-I", "-c", code], cwd=ROOT, capture_output=True, text=True, check=False,
                         env={"SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}, timeout=120)
    assert out.returncode == 0, out.stderr[-500:]
    assert out.stdout.strip().splitlines()[-1] == "[]"


def test_no_hosted_ai_module_references_local_model_loading() -> None:
    forbidden_imports = {"torch", "torchvision", "transformers", "diffusers", "onnxruntime"}
    forbidden_calls = {"from_pretrained", "hf_hub_download", "snapshot_download", "pipeline", "load_state_dict"}
    for path in (ROOT / "backend" / "ai").rglob("*.py"):
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not {a.name.split(".")[0] for a in node.names} & forbidden_imports, path
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in forbidden_imports, path
            elif isinstance(node, ast.Call):
                name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
                assert name not in forbidden_calls, (path, name)


def test_the_requirements_do_not_pull_in_local_inference_packages_for_this_feature() -> None:
    # The requirements file lives at the repo root or under backend/ depending on the deployment layout.
    candidates = [ROOT / "requirements.txt", ROOT / "backend" / "requirements.txt"]
    found = [p for p in candidates if p.is_file()]
    assert found, f"no requirements.txt in any of: {[str(p.relative_to(ROOT)) for p in candidates]}"
    lines = found[0].read_text(encoding="utf-8").splitlines()
    pinned = {line.split("==")[0].strip().lower() for line in lines if "==" in line}
    assert {"openai", "huggingface_hub", "pillow"} <= pinned
    assert "transformers" not in pinned and "torchvision" not in pinned


# ---- the real files --------------------------------------------------------------------------------------------------
BACKEND_ENV = ROOT / "backend" / ".env"


@pytest.mark.skipif(not BACKEND_ENV.is_file(), reason="backend/.env is not present (it is gitignored and local)")
def test_the_actual_backend_env_is_loaded_and_correctly_configured() -> None:
    """Static CONFIGURED check against the real file. Names only: no value is ever printed or asserted on."""
    settings = AISettings.from_env()  # same loader the backend process uses (backend/.env, real env vars win)
    bad = [c.name for c in d.config_checks(settings) if not c.ok]
    assert bad == [], bad
    status = AIService(settings).status()["tasks"]
    assert status["visual_investigation"]["state"] == "configured"
    assert status["visual_segmentation"]["state"] == "configured"
    assert status["visual_investigation"]["model"] == d.EXPECTED_QWEN_MODEL
    assert status["visual_segmentation"]["model"] == d.EXPECTED_SEGMENTATION_MODEL


@pytest.mark.skipif(not BACKEND_ENV.is_file(), reason="backend/.env is not present")
def test_the_env_file_is_gitignored() -> None:
    out = subprocess.run(["git", "check-ignore", "-q", "backend/.env"], cwd=ROOT, capture_output=True, check=False, timeout=30)
    assert out.returncode == 0


def test_env_example_contains_names_and_placeholders_only() -> None:
    text = (ROOT / "backend" / ".env.example").read_text(encoding="utf-8")
    assert not re.search(r"\b(hf_[A-Za-z0-9]{16,}|gsk_[A-Za-z0-9]{16,}|sk-[A-Za-z0-9]{16,})", text)
    for name in ("HF_TOKEN", "VISION_PROVIDER", "VISION_MODEL", "HF_INFERENCE_BASE_URL", "HF_INFERENCE_PROVIDER",
                 "HF_SEGMENTATION_MODEL", "HF_SEGMENTATION_ENDPOINT"):
        assert re.search(rf"^{name}=", text, re.MULTILINE), name
    assert "HF_TOKEN=REPLACE_WITH_HF_TOKEN" in text
    assert f"VISION_MODEL={d.EXPECTED_QWEN_MODEL}" in text and f"HF_SEGMENTATION_MODEL={d.EXPECTED_SEGMENTATION_MODEL}" in text

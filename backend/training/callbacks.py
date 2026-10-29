"""Callbacks for metrics and atomic checkpointing."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from stable_baselines3.common.callbacks import BaseCallback

from shared.schemas import new_uuid


class MetricsCallback(BaseCallback):
    def __init__(self, verbose: int = 0, max_history: int = 1000):
        super().__init__(verbose)
        self.max_history = max_history
        self.episodes: list[Dict[str, Any]] = []
        self.updates: list[Dict[str, Any]] = []

    def _on_step(self) -> bool:
        infos = self.locals.get("infos") or []
        for info in infos:
            if isinstance(info, dict) and info.get("episode"):
                ep = info["episode"]
                self.episodes.append(
                    {
                        "r": ep.get("r"),
                        "l": ep.get("l"),
                        "t": datetime.now(timezone.utc).isoformat(),
                    }
                )
        if len(self.episodes) > self.max_history:
            self.episodes = self.episodes[-self.max_history :]
        return True


class CheckpointCallback(BaseCallback):
    def __init__(
        self,
        save_freq: int = 1000,
        save_path: str = "./checkpoints",
        run_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        verbose: int = 0,
    ):
        super().__init__(verbose)
        self.save_freq = save_freq
        self.save_path = save_path
        self.run_id = run_id or new_uuid()
        self.metadata = metadata or {}
        os.makedirs(save_path, exist_ok=True)

    def _on_step(self) -> bool:
        if self.n_calls % self.save_freq == 0:
            self._save_checkpoint()
        return True

    def _save_checkpoint(self):
        checkpoint_id = new_uuid()
        filename = f"checkpoint_{checkpoint_id}.zip"
        final_path = os.path.join(self.save_path, filename)
        fd, tmp_path = tempfile.mkstemp(prefix="ckpt_", suffix=".tmp", dir=self.save_path)
        os.close(fd)
        try:
            self.model.save(tmp_path)
            with open(tmp_path, "rb") as f:
                data = f.read()
            h = hashlib.sha256(data).hexdigest()
            meta_path = final_path + ".meta.json"
            meta = {
                "checkpoint_id": checkpoint_id,
                "run_id": self.run_id,
                "path": final_path,
                "sha256": h,
                "num_timesteps": int(self.num_timesteps),
                "created_at": datetime.now(timezone.utc).isoformat(),
                **self.metadata,
            }
            fd2, tmp_meta = tempfile.mkstemp(prefix="ckpt_meta_", suffix=".tmp", dir=self.save_path)
            os.close(fd2)
            with open(tmp_meta, "w") as f:
                json.dump(meta, f, sort_keys=True)
            os.replace(tmp_path, final_path)
            os.replace(tmp_meta, meta_path)
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
            except Exception:
                pass
            raise

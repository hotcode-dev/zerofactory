"""Zero Factory — Profile Manager.

Automatically provisions and synchronizes the namespaced Zero Factory agent profiles:
- zf-orchestrator
- zf-builder
- zf-reviewer

Profiles are created inside ~/.hermes/profiles/ without overwriting user data.
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

_log = logging.getLogger("zerofactory.profiles")

ZF_PROFILES = ("zf-orchestrator", "zf-builder", "zf-reviewer")


def get_hermes_home() -> Path:
    """Return the active Hermes home directory (~/.hermes)."""
    env_home = os.environ.get("HERMES_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    return (Path.home() / ".hermes").resolve()


def get_plugin_root() -> Path:
    """Return the root path of the zerofactory plugin."""
    return Path(__file__).resolve().parent


def get_root_model_config() -> Dict[str, Any]:
    """Inspect ~/.hermes/config.yaml for default model/provider settings to inherit."""
    if not yaml:
        return {}
    root_cfg_path = get_hermes_home() / "config.yaml"
    if not root_cfg_path.exists():
        return {}
    try:
        data = yaml.safe_load(root_cfg_path.read_text(encoding="utf-8")) or {}
        model_cfg = data.get("model")
        if isinstance(model_cfg, dict):
            return {"model": model_cfg}
    except Exception as e:
        _log.warning("Could not read root model config: %s", e)
    return {}


def ensure_zf_profiles(force: bool = False, update_prompts: bool = False) -> Dict[str, List[str]]:
    """Ensure that zf-orchestrator, zf-builder, and zf-reviewer exist in ~/.hermes/profiles.

    Args:
        force: If True, overwrite config.yaml and SOUL.md with templates even if they exist.
        update_prompts: If True, refresh SOUL.md without touching config.yaml or .env.

    Returns:
        Dict with lists of 'created', 'updated', and 'existing' profiles.
    """
    hermes_home = get_hermes_home()
    profiles_dir = hermes_home / "profiles"

    # Handle case where profiles_dir is a broken symlink or points to repo
    if profiles_dir.is_symlink():
        try:
            target = profiles_dir.resolve()
            if not target.exists():
                profiles_dir.unlink()
                profiles_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    profiles_dir.mkdir(parents=True, exist_ok=True)
    plugin_root = get_plugin_root()
    templates_dir = plugin_root / "templates"
    skill_src = plugin_root / "skills" / "zerofactory-orchestration"

    root_model = get_root_model_config()
    res = {"created": [], "updated": [], "existing": []}

    for role in ZF_PROFILES:
        target_dir = profiles_dir / role
        is_new = not target_dir.exists()

        if is_new:
            target_dir.mkdir(parents=True, exist_ok=True)
            for sub in ("cron", "sessions", "memories", "logs", "skills"):
                (target_dir / sub).mkdir(parents=True, exist_ok=True)

        template_role_dir = templates_dir / role
        soul_src = template_role_dir / "SOUL.md"
        config_src = template_role_dir / "config.yaml"
        soul_dst = target_dir / "SOUL.md"
        config_dst = target_dir / "config.yaml"
        env_dst = target_dir / ".env"

        # 1. Seed or update SOUL.md
        if soul_src.exists():
            if is_new or force or update_prompts:
                shutil.copy2(soul_src, soul_dst)

        # 2. Seed config.yaml
        if config_src.exists():
            if is_new or force:
                if yaml and root_model:
                    try:
                        base_cfg = yaml.safe_load(config_src.read_text(encoding="utf-8")) or {}
                        # Merge inherited model config if profile doesn't define a model
                        if "model" not in base_cfg and "model" in root_model:
                            base_cfg["model"] = root_model["model"]
                        config_dst.write_text(yaml.dump(base_cfg, sort_keys=False), encoding="utf-8")
                    except Exception:
                        shutil.copy2(config_src, config_dst)
                else:
                    shutil.copy2(config_src, config_dst)

        # 3. Seed .env if missing
        if not env_dst.exists():
            env_dst.write_text("# Zero Factory Profile Environment\n", encoding="utf-8")
            try:
                os.chmod(str(env_dst), 0o600)
            except OSError:
                pass

        # 4. Link or copy orchestration skill
        if skill_src.exists():
            dest_skill = target_dir / "skills" / "zerofactory-orchestration"
            if not dest_skill.exists():
                try:
                    dest_skill.symlink_to(skill_src, target_is_directory=True)
                except Exception:
                    shutil.copytree(skill_src, dest_skill, dirs_exist_ok=True)

        if is_new:
            res["created"].append(role)
        elif force or update_prompts:
            res["updated"].append(role)
        else:
            res["existing"].append(role)

    return res

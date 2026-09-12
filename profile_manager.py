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


def get_hermes_root() -> Path:
    """Return the base ~/.hermes directory, stripping any active profile path."""
    env_home = os.environ.get("HERMES_HOME")
    if env_home:
        p = Path(env_home).expanduser().resolve()
        if "profiles" in p.parts:
            idx = p.parts.index("profiles")
            return Path(*p.parts[:idx])
        return p
    return (Path.home() / ".hermes").resolve()


def get_hermes_home() -> Path:
    """Return the base Hermes home directory (~/.hermes)."""
    return get_hermes_root()


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

    # Ensure orchestration skill is also available in root ~/.hermes/skills/
    root_skills = hermes_home / "skills"
    if skill_src.exists() and root_skills.exists():
        root_skill_dst = root_skills / "zerofactory-orchestration"
        if not root_skill_dst.exists() and not root_skill_dst.is_symlink():
            try:
                root_skill_dst.symlink_to(skill_src, target_is_directory=True)
            except Exception:
                pass

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

        # 5. Ensure profile's plugins/ directory and symlinks exist
        prof_plugins = target_dir / "plugins"
        prof_plugins.mkdir(parents=True, exist_ok=True)
        p_link = prof_plugins / "zerofactory"
        if not p_link.exists() and not p_link.is_symlink():
            try:
                p_link.symlink_to(plugin_root, target_is_directory=True)
            except Exception:
                pass

        # 6. Ensure plugins.enabled in config.yaml
        if yaml and config_dst.exists():
            try:
                cfg_data = yaml.safe_load(config_dst.read_text(encoding="utf-8")) or {}
                plugins_sec = cfg_data.setdefault("plugins", {})
                enabled_list = plugins_sec.setdefault("enabled", [])
                cfg_modified = False
                if "zerofactory" not in enabled_list:
                    enabled_list.append("zerofactory")
                    cfg_modified = True
                if cfg_modified:
                    config_dst.write_text(yaml.dump(cfg_data, sort_keys=False), encoding="utf-8")
            except Exception as e:
                _log.warning("Could not ensure plugins in %s: %s", config_dst, e)

        if is_new:
            res["created"].append(role)
        elif force or update_prompts:
            res["updated"].append(role)
        else:
            res["existing"].append(role)

    # Automatically synchronize root and profile plugin symlinks
    sym_res = ensure_plugin_symlinks()
    res["plugin_symlinks"] = sym_res.get("linked", [])

    # Automatically deploy scripts to ~/.hermes/scripts and profile scripts dirs
    script_res = ensure_script_files()
    res["scripts"] = script_res.get("copied", [])

    return res


def ensure_plugin_symlinks() -> Dict[str, Any]:
    """Ensure plugin symlink (zerofactory) and config entries exist in:
    1. Root ~/.hermes/plugins/ and ~/.hermes/config.yaml
    2. ~/.hermes/profiles/<role>/plugins/ and config.yaml for each zf-* profile
    3. Legacy profiles (orchestrator, builder, reviewer) if they exist
    """
    hermes_home = get_hermes_home()
    plugin_root = get_plugin_root()
    profiles_dir = hermes_home / "profiles"

    linked: List[str] = []

    def _link_in_dir(target_plugins_dir: Path):
        target_plugins_dir.mkdir(parents=True, exist_ok=True)
        link_path = target_plugins_dir / "zerofactory"
        try:
            if link_path.is_symlink() or link_path.exists():
                if link_path.is_symlink():
                    try:
                        cur_target = link_path.resolve()
                        if cur_target == plugin_root.resolve():
                            pass
                        else:
                            link_path.unlink()
                            link_path.symlink_to(plugin_root, target_is_directory=True)
                    except Exception:
                        link_path.unlink()
                        link_path.symlink_to(plugin_root, target_is_directory=True)
                elif link_path.is_dir():
                    shutil.rmtree(link_path)
                    link_path.symlink_to(plugin_root, target_is_directory=True)
                else:
                    link_path.unlink()
                    link_path.symlink_to(plugin_root, target_is_directory=True)
            else:
                link_path.symlink_to(plugin_root, target_is_directory=True)
            linked.append(str(link_path))
        except Exception as e:
            _log.warning("Could not link plugin in %s: %s", target_plugins_dir, e)

    def _enable_in_config(cfg_path: Path):
        if not yaml or not cfg_path.exists():
            return
        try:
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            plugins_sec = cfg.setdefault("plugins", {})
            enabled = plugins_sec.setdefault("enabled", [])
            changed = False
            if "zerofactory" not in enabled:
                enabled.append("zerofactory")
                changed = True
            entries = plugins_sec.setdefault("entries", {})
            if "zerofactory" not in entries:
                entries["zerofactory"] = {"allow_tool_override": False}
                changed = True
            if changed:
                cfg_path.write_text(yaml.dump(cfg, sort_keys=False), encoding="utf-8")
        except Exception as e:
            _log.warning("Could not update plugins.enabled in %s: %s", cfg_path, e)

    # 1. Root ~/.hermes/plugins and ~/.hermes/config.yaml
    _link_in_dir(hermes_home / "plugins")
    _enable_in_config(hermes_home / "config.yaml")

    # 2. ZF profiles
    for role in ZF_PROFILES:
        prof_dir = profiles_dir / role
        if prof_dir.exists():
            _link_in_dir(prof_dir / "plugins")
            _enable_in_config(prof_dir / "config.yaml")

    # 3. Legacy profiles (if present)
    for legacy_role in ("orchestrator", "builder", "reviewer"):
        prof_dir = profiles_dir / legacy_role
        if prof_dir.exists():
            _link_in_dir(prof_dir / "plugins")
            _enable_in_config(prof_dir / "config.yaml")

    return {"linked": linked}


def ensure_script_files() -> Dict[str, Any]:
    """Deploy and synchronize Zero Factory automation scripts into Hermes scripts directories.

    Hermes cron job security model mandates that `script` targets must resolve inside
    HERMES_HOME/scripts/ (or <profile>/scripts/). To satisfy this sandbox without
    triggering symlink escape checks, scripts are copied directly.
    """
    hermes_home = get_hermes_home()
    plugin_root = get_plugin_root()
    src_scripts_dir = plugin_root / "scripts"
    profiles_dir = hermes_home / "profiles"

    if not src_scripts_dir.is_dir():
        return {"copied": []}

    target_script_dirs = [hermes_home / "scripts"]
    for role in ZF_PROFILES:
        target_script_dirs.append(profiles_dir / role / "scripts")
    for legacy_role in ("orchestrator", "builder", "reviewer"):
        prof_dir = profiles_dir / legacy_role
        if prof_dir.exists():
            target_script_dirs.append(prof_dir / "scripts")

    copied: List[str] = []
    for script_file in src_scripts_dir.glob("*.py"):
        if not script_file.is_file():
            continue
        content = script_file.read_bytes()
        for target_dir in target_script_dirs:
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                dest_file = target_dir / script_file.name
                # Only write if missing or content changed
                if not dest_file.exists() or dest_file.read_bytes() != content:
                    if dest_file.is_symlink():
                        dest_file.unlink()
                    dest_file.write_bytes(content)
                    try:
                        os.chmod(str(dest_file), 0o755)
                    except OSError:
                        pass
                copied.append(str(dest_file))
            except Exception as e:
                _log.warning("Could not sync script %s to %s: %s", script_file.name, target_dir, e)

    return {"copied": copied}


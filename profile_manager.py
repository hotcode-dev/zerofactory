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
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

_log = logging.getLogger("zerofactory.profiles")

ZF_PROFILES = ("zf-orchestrator", "zf-builder", "zf-reviewer")

# All HERMES_LANGFUSE_* keys written to .env files by sync_langfuse_profiles().
# Used to scrub stale credentials from every profile .env when Langfuse is disabled.
LANGFUSE_ENV_KEYS: Set[str] = {
    "HERMES_LANGFUSE_PUBLIC_KEY",
    "HERMES_LANGFUSE_SECRET_KEY",
    "HERMES_LANGFUSE_BASE_URL",
    "HERMES_LANGFUSE_CAPTURE",
    "HERMES_LANGFUSE_ENV",
}


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
    """Return the canonical root path of the zerofactory plugin.

    If executed from inside an isolated git worktree (e.g. `*-worktrees/<task_id>`),
    this resolves to the primary repository root to ensure plugin symlinks in
    ~/.hermes/plugins/ and profile directories never point to transient worktrees
    that will be removed when the task completes.
    """
    cur = Path(__file__).resolve().parent

    # 1. Check if .git is a worktree pointer file
    git_entry = cur / ".git"
    if git_entry.is_file():
        try:
            content = git_entry.read_text(encoding="utf-8").strip()
            if content.startswith("gitdir:"):
                gitdir_str = content.split(":", 1)[1].strip()
                gitdir_path = Path(gitdir_str).resolve()
                if "worktrees" in gitdir_path.parts:
                    idx = gitdir_path.parts.index("worktrees")
                    dot_git = Path(*gitdir_path.parts[:idx])
                    main_repo = dot_git.parent
                    if (main_repo / "plugin.yaml").exists():
                        return main_repo
        except Exception:
            pass

    # 2. Check if git common dir points to main repo
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=str(cur),
            capture_output=True,
            text=True,
            timeout=3,
        )
        if res.returncode == 0:
            common_git = Path(res.stdout.strip()).resolve()
            main_repo = common_git.parent
            if (main_repo / "plugin.yaml").exists():
                return main_repo
    except Exception:
        pass

    # 3. Path heuristic: if within a `<name>-worktrees/<task_id>` folder
    if "-worktrees" in cur.parent.name:
        candidate_repo = cur.parent.parent / cur.parent.name.replace("-worktrees", "")
        if (candidate_repo / "plugin.yaml").exists():
            return candidate_repo

    return cur


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

    # Ensure all plugin skills are available in root ~/.hermes/skills/
    root_skills = hermes_home / "skills"
    skills_dir = plugin_root / "skills"
    if skills_dir.exists() and root_skills.exists():
        for skill_dir in skills_dir.iterdir():
            if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                dst = root_skills / skill_dir.name
                if dst.is_symlink() and not dst.exists():
                    try:
                        dst.unlink()
                    except Exception:
                        pass
                if not dst.exists() and not dst.is_symlink():
                    try:
                        dst.symlink_to(skill_dir, target_is_directory=True)
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
            if not soul_dst.exists() or is_new or force or update_prompts:
                shutil.copy2(soul_src, soul_dst)

        # 2. Seed config.yaml
        if config_src.exists():
            if not config_dst.exists() or is_new or force:
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

        # 4. Link or copy skills from plugin_root / "skills"
        if skills_dir.exists():
            profile_skills_dir = target_dir / "skills"
            profile_skills_dir.mkdir(parents=True, exist_ok=True)
            for skill_dir in skills_dir.iterdir():
                if skill_dir.is_dir() and (skill_dir / "SKILL.md").exists():
                    sname = skill_dir.name
                    # If a skill has a role prefix (e.g. zf-builder-), only link to that role
                    if sname.startswith("zf-") and not sname.startswith(f"{role}-"):
                        old_link = profile_skills_dir / sname
                        if old_link.exists() or old_link.is_symlink():
                            try:
                                if old_link.is_symlink() or old_link.is_file():
                                    old_link.unlink()
                                elif old_link.is_dir():
                                    shutil.rmtree(old_link)
                            except Exception:
                                pass
                        continue

                    dest_skill = profile_skills_dir / sname
                    if dest_skill.is_symlink() and not dest_skill.exists():
                        try:
                            dest_skill.unlink()
                        except Exception:
                            pass
                    if not dest_skill.exists() and not dest_skill.is_symlink():
                        try:
                            dest_skill.symlink_to(skill_dir, target_is_directory=True)
                        except Exception:
                            shutil.copytree(skill_dir, dest_skill, dirs_exist_ok=True)

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

    # Automatically synchronize Langfuse observability across profiles
    try:
        lf_res = sync_langfuse_profiles()
        res["langfuse_synced"] = lf_res.get("synced", [])
    except Exception as e:
        _log.warning("Could not sync Langfuse settings across profiles: %s", e)

    return res


def ensure_plugin_symlinks() -> Dict[str, Any]:
    """Ensure plugin symlink (zerofactory) and config entries exist in:
    1. Root ~/.hermes/plugins/ and ~/.hermes/config.yaml
    2. ~/.hermes/profiles/<role>/plugins/ and config.yaml for each zf-* profile
    """
    hermes_home = get_hermes_home()
    plugin_root = get_plugin_root()
    profiles_dir = hermes_home / "profiles"

    # Guardrail: NEVER symlink to a transient git worktree directory
    if "-worktrees" in str(plugin_root) or (plugin_root / ".git").is_file():
        _log.warning("Refusing to create plugin symlink to git worktree directory: %s", plugin_root)
        return {"linked": []}

    linked: List[str] = []

    def _link_in_dir(target_plugins_dir: Path):
        target_plugins_dir.mkdir(parents=True, exist_ok=True)
        link_path = target_plugins_dir / "zerofactory"
        try:
            if link_path.is_symlink() or link_path.exists():
                if link_path.is_symlink():
                    try:
                        cur_target = link_path.resolve()
                        # If existing symlink points to a transient worktree or is broken, unlink it
                        if "-worktrees" in str(cur_target) or not cur_target.exists():
                            link_path.unlink()
                            link_path.symlink_to(plugin_root, target_is_directory=True)
                        elif cur_target == plugin_root.resolve():
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


def update_env_file(env_path: Path, updates: Dict[str, str], remove_keys: Optional[Set[str]] = None) -> None:
    """Update or insert key=value pairs in an environment file while preserving comments and other keys."""
    env_path.parent.mkdir(parents=True, exist_ok=True)
    existing_lines: List[str] = []
    if env_path.exists():
        try:
            existing_lines = env_path.read_text(encoding="utf-8").splitlines()
        except Exception as e:
            _log.warning("Could not read %s: %s", env_path, e)

    remaining_updates = dict(updates)
    remove_set = remove_keys or set()
    new_lines: List[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in remove_set:
                continue
            if key in remaining_updates:
                new_val = remaining_updates.pop(key)
                new_lines.append(f"{key}={new_val}")
                continue
        new_lines.append(line)

    for key, val in remaining_updates.items():
        new_lines.append(f"{key}={val}")

    content = "\n".join(new_lines).strip() + "\n"
    env_path.write_text(content, encoding="utf-8")
    try:
        os.chmod(str(env_path), 0o600)
    except OSError:
        pass


def update_config_yaml_plugins(config_path: Path, enable_plugin: Optional[str] = None, disable_plugin: Optional[str] = None) -> None:
    """Update plugins.enabled list in config.yaml without altering other configuration sections."""
    if not yaml or not config_path.exists():
        return
    try:
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        plugins_sec = cfg.setdefault("plugins", {})
        enabled_list = plugins_sec.setdefault("enabled", [])
        changed = False

        if enable_plugin and enable_plugin not in enabled_list:
            enabled_list.append(enable_plugin)
            changed = True
        if disable_plugin and disable_plugin in enabled_list:
            enabled_list.remove(disable_plugin)
            changed = True

        if changed:
            config_path.write_text(yaml.dump(cfg, sort_keys=False), encoding="utf-8")
    except Exception as e:
        _log.warning("Could not update plugins in %s: %s", config_path, e)


def sync_langfuse_profiles(settings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Synchronize Langfuse credentials and plugin enablement across all Hermes profiles.

    Targets root (~/.hermes/) and all agent profile directories (~/.hermes/profiles/*).

    When disabled, every HERMES_LANGFUSE_* key is removed from each target .env file
    (stale secrets are scrubbed) and ``langfuse`` is removed from each config.yaml
    ``plugins.enabled`` list. Note: explicitly clearing an individual key while the
    feature stays enabled (e.g. ``langfuse_secret_key: ""``) writes an empty value —
    keys are only removed on full disable.
    """
    if settings is None:
        try:
            import sqlite3
            from settings import load_settings

            db_override = os.environ.get("ZEROFACTORY_DB")
            db_p = Path(db_override) if db_override else (get_hermes_home() / "zerofactory.db")
            if db_p.exists():
                with sqlite3.connect(str(db_p), timeout=2.0) as conn:
                    conn.row_factory = sqlite3.Row
                    settings = load_settings(conn)
            else:
                from settings import DEFAULT_SETTING_VALUES
                settings = {k: DEFAULT_SETTING_VALUES.get(k) for k in DEFAULT_SETTING_VALUES}
        except Exception as e:
            _log.debug("Could not load settings for Langfuse sync: %s", e)
            settings = {}

    hermes_home = get_hermes_home()
    profiles_dir = hermes_home / "profiles"

    target_dirs: List[Path] = [hermes_home]
    if profiles_dir.is_dir():
        for child in sorted(profiles_dir.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                target_dirs.append(child)

    # Ensure all canonical ZF profiles are included if they exist
    for role in ZF_PROFILES:
        r_dir = profiles_dir / role
        if r_dir.exists() and r_dir not in target_dirs:
            target_dirs.append(r_dir)

    is_enabled = bool(settings.get("langfuse_enabled"))
    synced_targets: List[str] = []

    if is_enabled:
        env_updates = {
            "HERMES_LANGFUSE_PUBLIC_KEY": str(settings.get("langfuse_public_key") or "").strip(),
            "HERMES_LANGFUSE_SECRET_KEY": str(settings.get("langfuse_secret_key") or "").strip(),
            "HERMES_LANGFUSE_BASE_URL": str(settings.get("langfuse_base_url") or "https://cloud.langfuse.com").strip(),
            "HERMES_LANGFUSE_CAPTURE": str(settings.get("langfuse_capture_mode") or "sanitized").strip(),
            "HERMES_LANGFUSE_ENV": str(settings.get("langfuse_env") or "zerofactory").strip(),
        }
        for target in target_dirs:
            update_env_file(target / ".env", env_updates)
            update_config_yaml_plugins(target / "config.yaml", enable_plugin="langfuse")
            synced_targets.append(str(target))
    else:
        for target in target_dirs:
            # Scrub stale Langfuse credentials (incl. secret key) from every .env
            # so disabling the feature leaves no plaintext secrets behind.
            update_env_file(target / ".env", {}, remove_keys=LANGFUSE_ENV_KEYS)
            update_config_yaml_plugins(target / "config.yaml", disable_plugin="langfuse")
            synced_targets.append(str(target))

    return {"enabled": is_enabled, "synced": synced_targets}


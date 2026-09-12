"""Read-only operator config checks; never open a job record or key contents."""
import os
from pathlib import Path
import plistlib
import stat
import sys


def require(condition, category):
    if not condition:
        raise ValueError(category)


def private_file(path):
    info = path.lstat()
    return (stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o600 and info.st_nlink == 1)


def validate(config):
    root = Path.home() / "Library/Application Support/chatgpt-codex-bridge"
    require(str(config) == str(root / "config.plist")
            and str(config) == str(config.resolve(strict=True))
            and private_file(config), "OPERATOR_CONFIG_REJECTED")
    root_info = root.stat()
    require(root_info.st_uid == os.getuid() and not root_info.st_mode & 0o022,
            "OPERATOR_CONFIG_REJECTED")
    with config.open("rb") as stream:
        data = plistlib.load(stream)
    require(isinstance(data, dict), "OPERATOR_CONFIG_REJECTED")
    require(data.get("sandbox") == "workspace-write"
            and data.get("approval_policy") == "never", "MANAGED_POLICY_REJECTED")
    raw = data.get("job_state_dir")
    require(isinstance(raw, str) and bool(raw), "JOB_STATE_DIR_REQUIRED")
    require(not any(ord(char) < 32 or ord(char) == 127 for char in raw),
            "JOB_STATE_DIR_REJECTED")
    store = Path(raw)
    require(store.is_absolute() and raw == str(store.resolve(strict=True)),
            "JOB_STATE_DIR_REJECTED")
    require(store.parent == root and store.name not in ("jobs-v2", "jobs-v3", "jobs-v4"),
            "JOB_STATE_DIR_REJECTED")
    workspace = Path(data["workspace"]).resolve(strict=True)
    require(store != workspace and store not in workspace.parents
            and workspace not in store.parents, "JOB_STATE_DIR_REJECTED")
    info = store.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o700, "JOB_STATE_DIR_REJECTED")
    key = store / "capability.key"
    if key.exists() or key.is_symlink():
        require(private_file(key) and key.stat().st_size == 32, "STORE_KEY_REJECTED")


def main():
    try:
        mode, raw = sys.argv[1:]
        config = Path(raw)
        if mode == "maintenance":
            if config.exists() or config.is_symlink():
                require(not config.is_symlink() and config.is_file(), "OPERATOR_CONFIG_REJECTED")
                with config.open("rb") as stream:
                    data = plistlib.load(stream)
                require(isinstance(data, dict), "OPERATOR_CONFIG_REJECTED")
                require("job_state_dir" not in data and data.get("preset") != "managed-repo",
                        "EXPLICIT_STORE_REQUIRES_REVIEWED_RECOVERY")
        else:
            require(mode == "validate", "OPERATOR_CONFIG_REJECTED")
            # Preserve the raw spelling check before Path can normalize it.
            require(raw == str(config), "OPERATOR_CONFIG_REJECTED")
            validate(config)
    except ValueError as error:
        known = {"OPERATOR_CONFIG_REJECTED", "MANAGED_POLICY_REJECTED",
                 "JOB_STATE_DIR_REQUIRED", "JOB_STATE_DIR_REJECTED",
                 "STORE_KEY_REJECTED", "EXPLICIT_STORE_REQUIRES_REVIEWED_RECOVERY"}
        print(str(error) if str(error) in known else "OPERATOR_CONFIG_REJECTED", file=sys.stderr)
        return 64
    except (OSError, KeyError, TypeError, RuntimeError, plistlib.InvalidFileException):
        print("OPERATOR_CONFIG_REJECTED", file=sys.stderr)
        return 64
    return 0


if __name__ == "__main__":
    sys.exit(main())

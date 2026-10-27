import os
import pwd
import subprocess
from pathlib import Path

LOGGER_STATE_DIR = Path("/var/lib/flight-tracker-logger")
PUBLIC_KEY_DIR = Path("/opt/flight-tracker/logger/public")
LOG_DIR = Path("/var/log/flight-tracker")
PRIVATE_KEY = LOGGER_STATE_DIR / "id_ed25519"
SHARED_PUBLIC_KEY = PUBLIC_KEY_DIR / "id_ed25519.pub"


def ensure_directory(path: Path, mode: int, owner: int, group: int) -> None:
    path.mkdir(mode=mode, parents=True, exist_ok=True)
    os.chown(path, owner, group)
    os.chmod(path, mode)


def main() -> None:
    account = pwd.getpwnam("vagrant")
    ensure_directory(LOGGER_STATE_DIR, 0o700, account.pw_uid, account.pw_gid)
    ensure_directory(LOGGER_STATE_DIR / "cursors", 0o700, account.pw_uid, account.pw_gid)
    ensure_directory(LOG_DIR, 0o755, 0, 0)
    ensure_directory(LOG_DIR / "containers", 0o750, account.pw_uid, account.pw_gid)
    if not PUBLIC_KEY_DIR.is_dir():
        raise SystemExit(f"Logger public-key share is not mounted: {PUBLIC_KEY_DIR}")

    metrics_log = LOG_DIR / "metrics.log"
    metrics_log.touch(exist_ok=True)
    os.chown(metrics_log, account.pw_uid, account.pw_gid)
    os.chmod(metrics_log, 0o640)

    if not PRIVATE_KEY.exists():
        subprocess.run(
            [
                "runuser",
                "-u",
                "vagrant",
                "--",
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-C",
                "flight-tracker-logger@database",
                "-f",
                str(PRIVATE_KEY),
            ],
            check=True,
        )
    elif PRIVATE_KEY.stat().st_size == 0:
        raise SystemExit(f"Logger private SSH key is empty: {PRIVATE_KEY}")

    derived_public_key = subprocess.run(
        ["runuser", "-u", "vagrant", "--", "ssh-keygen", "-y", "-f", str(PRIVATE_KEY)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not derived_public_key:
        raise SystemExit(f"Logger private SSH key is invalid: {PRIVATE_KEY}")

    for public_key_path in (PRIVATE_KEY.with_suffix(".pub"), SHARED_PUBLIC_KEY):
        public_key_path.write_text(f"{derived_public_key}\n", encoding="utf-8")
        os.chown(public_key_path, account.pw_uid, account.pw_gid)
        os.chmod(public_key_path, 0o644)
    os.chown(PRIVATE_KEY, account.pw_uid, account.pw_gid)
    os.chmod(PRIVATE_KEY, 0o600)


if __name__ == "__main__":
    main()

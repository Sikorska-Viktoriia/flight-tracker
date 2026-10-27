import os
import pwd
import subprocess
import tempfile
from pathlib import Path

PUBLIC_KEY = Path("/tmp/flight-tracker-host.pub")
AUTHORIZED_KEYS = Path("/home/vagrant/.ssh/authorized_keys")


def main() -> None:
    if not PUBLIC_KEY.is_file() or PUBLIC_KEY.stat().st_size == 0:
        raise SystemExit(f"SSH public key was not provided: {PUBLIC_KEY}")
    key = PUBLIC_KEY.read_text(encoding="utf-8")
    if "\n" in key.rstrip("\n") or not key.strip():
        raise SystemExit(f"Expected exactly one SSH public key in {PUBLIC_KEY}.")
    subprocess.run(["ssh-keygen", "-lf", str(PUBLIC_KEY)], check=True, capture_output=True)

    account = pwd.getpwnam("vagrant")
    AUTHORIZED_KEYS.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chown(AUTHORIZED_KEYS.parent, account.pw_uid, account.pw_gid)
    os.chmod(AUTHORIZED_KEYS.parent, 0o700)
    existing = (
        AUTHORIZED_KEYS.read_text(encoding="utf-8").splitlines()
        if AUTHORIZED_KEYS.exists()
        else []
    )
    entry = key.strip()
    if entry not in existing:
        existing.append(entry)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".authorized_keys-",
        dir=AUTHORIZED_KEYS.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write("\n".join(existing) + "\n")
        os.chown(temporary_name, account.pw_uid, account.pw_gid)
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, AUTHORIZED_KEYS)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    PUBLIC_KEY.unlink()


if __name__ == "__main__":
    main()

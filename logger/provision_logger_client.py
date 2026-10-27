import os
import pwd
import subprocess
import tempfile
from pathlib import Path

PUBLIC_KEY = Path("/opt/flight-tracker/logger/public/id_ed25519.pub")
AUTHORIZED_KEYS = Path("/home/vagrant/.ssh/authorized_keys")
KEY_COMMENT = "flight-tracker-logger"
REMOTE_COMMAND = "/usr/local/sbin/flight-tracker-logger-remote"


def main() -> None:
    if not PUBLIC_KEY.is_file():
        raise SystemExit(
            f"Logger public key is missing: {PUBLIC_KEY}. Provision the database VM first."
        )
    subprocess.run(["ssh-keygen", "-lf", str(PUBLIC_KEY)], check=True, capture_output=True)
    key_fields = PUBLIC_KEY.read_text(encoding="utf-8").split()
    if len(key_fields) < 2:
        raise SystemExit(f"Invalid logger public key: {PUBLIC_KEY}")

    account = pwd.getpwnam("vagrant")
    AUTHORIZED_KEYS.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chown(AUTHORIZED_KEYS.parent, account.pw_uid, account.pw_gid)
    os.chmod(AUTHORIZED_KEYS.parent, 0o700)

    existing = (
        AUTHORIZED_KEYS.read_text(encoding="utf-8").splitlines()
        if AUTHORIZED_KEYS.exists()
        else []
    )
    entries = [line for line in existing if f" {KEY_COMMENT}" not in line]
    entries.append(
        f'restrict,command="{REMOTE_COMMAND}" {key_fields[0]} {key_fields[1]} {KEY_COMMENT}'
    )
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".authorized_keys-",
        dir=AUTHORIZED_KEYS.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write("\n".join(entries) + "\n")
        os.chown(temporary_name, account.pw_uid, account.pw_gid)
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, AUTHORIZED_KEYS)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


if __name__ == "__main__":
    main()

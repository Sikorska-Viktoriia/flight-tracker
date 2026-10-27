import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from string import Template

START = "# BEGIN flight-tracker-vagrant"
END = "# END flight-tracker-vagrant"
CONFIG_TEMPLATE = Path(__file__).resolve().parents[1] / "configs/ssh/host-config.template"


def public_key_path() -> Path:
    configured = os.environ.get("VAGRANT_SSH_PUBLIC_KEY", "")
    if configured:
        return Path(configured).expanduser()

    for name in ("id_ed25519.pub", "id_ecdsa.pub", "id_rsa.pub"):
        candidate = Path.home() / ".ssh" / name
        if candidate.is_file():
            return candidate
    raise SystemExit("No SSH public key found. Set VAGRANT_SSH_PUBLIC_KEY to its path.")


def verify_key_pair(public_key: Path, private_key: Path) -> None:
    if not public_key.is_file():
        raise SystemExit(f"SSH public key not found: {public_key}")
    if not private_key.is_file():
        raise SystemExit(f"Matching private key not found: {private_key}")

    public_fingerprint = subprocess.run(
        ["ssh-keygen", "-lf", str(public_key)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()[1]
    private_public_key = subprocess.run(
        ["ssh-keygen", "-y", "-f", str(private_key)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    private_fingerprint = subprocess.run(
        ["ssh-keygen", "-lf", "-"],
        input=private_public_key,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()[1]
    if not public_fingerprint or public_fingerprint != private_fingerprint:
        raise SystemExit("The public and private SSH keys do not match.")


def replace_managed_block(config: Path, key: str, bastion_host: str) -> None:
    contents = config.read_text(encoding="utf-8")
    if (START in contents) != (END in contents):
        raise SystemExit("SSH config has an incomplete Flight Tracker managed block.")
    if START in contents:
        before, remainder = contents.split(START, 1)
        _, after = remainder.split(END, 1)
        contents = before + after.lstrip("\n")

    managed_config = Template(CONFIG_TEMPLATE.read_text(encoding="utf-8")).substitute(
        BASTION_HOST=bastion_host,
        IDENTITY_FILE=key.replace("\\", "\\\\").replace('"', '\\"'),
    )
    for name in ("bastion", "database", "fetcher", "history", "ui"):
        for line in contents.splitlines():
            fields = line.split()
            if fields and fields[0].lower() == "host" and name in fields[1:]:
                raise SystemExit(
                    f"SSH alias {name!r} is already configured outside the managed block."
                )

    updated = managed_config.rstrip() + "\n\n" + contents.lstrip("\n")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".flight-tracker-ssh-", dir=config.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(updated)
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, config)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def main() -> None:
    public_key = public_key_path()
    private_key = (
        Path(sys.argv[1]).expanduser()
        if len(sys.argv) > 1
        else public_key.with_suffix("")
    )
    verify_key_pair(public_key, private_key)

    bastion_host = os.environ.get("BASTION_HOST", "192.168.56.20")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", bastion_host):
        raise SystemExit("BASTION_HOST must be an IP address or hostname.")

    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(ssh_dir, 0o700)
    config = ssh_dir / "config"
    config.touch(mode=0o600, exist_ok=True)
    os.chmod(config, 0o600)
    replace_managed_block(config, str(private_key.resolve()), bastion_host)
    print(
        "SSH aliases configured through the bastion. Connect with: "
        "ssh database (or bastion, fetcher, history, ui)."
    )


if __name__ == "__main__":
    main()

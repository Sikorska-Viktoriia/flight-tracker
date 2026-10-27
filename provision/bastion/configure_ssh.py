import os
import pwd
import subprocess
import tempfile
from pathlib import Path
from string import Template

JUMP_USER = "flight-jump"
JUMP_KEY = Path("/tmp/flight-tracker-jump.pub")
HOST_KEY = Path("/tmp/flight-tracker-host.pub")
JUMP_AUTHORIZED_KEYS = Path("/home/flight-jump/.ssh/authorized_keys")
VAGRANT_AUTHORIZED_KEYS = Path("/home/vagrant/.ssh/authorized_keys")
AUTHORIZED_KEYS_TEMPLATE = (
    Path(__file__).resolve().parents[2] / "configs/ssh/bastion-authorized-keys.template"
)


def read_key(path: Path) -> tuple[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) != 1:
        raise SystemExit(f"Expected exactly one SSH public key in {path}.")
    fields = lines[0].split()
    if len(fields) < 2 or not (
        fields[0] in {"ssh-ed25519", "ssh-rsa"} or fields[0].startswith("ecdsa-sha2-")
    ):
        raise SystemExit(f"Invalid SSH public key in {path}.")
    subprocess.run(["ssh-keygen", "-lf", str(path)], check=True, capture_output=True)
    return fields[0], fields[1]


def ensure_jump_user() -> pwd.struct_passwd:
    try:
        account = pwd.getpwnam(JUMP_USER)
    except KeyError:
        subprocess.run(
            [
                "useradd",
                "--create-home",
                "--user-group",
                "--shell",
                "/usr/sbin/nologin",
                JUMP_USER,
            ],
            check=True,
        )
    else:
        subprocess.run(["usermod", "--shell", "/usr/sbin/nologin", JUMP_USER], check=True)
        return account
    return pwd.getpwnam(JUMP_USER)


def write_authorized_keys(path: Path, contents: str, owner: int, group: int) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chown(path.parent, owner, group)
    os.chmod(path.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".authorized_keys-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(contents)
        os.chown(temporary_name, owner, group)
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def install_jump_key(account: pwd.struct_passwd, key_type: str, key_data: str) -> None:
    key_line = Template(AUTHORIZED_KEYS_TEMPLATE.read_text(encoding="utf-8")).substitute(
        KEY_TYPE=key_type,
        KEY_DATA=key_data,
    )
    write_authorized_keys(
        JUMP_AUTHORIZED_KEYS,
        key_line,
        account.pw_uid,
        account.pw_gid,
    )


def remove_vagrant_host_key(host_key_type: str, host_key_data: str) -> None:
    if not VAGRANT_AUTHORIZED_KEYS.is_file():
        return
    vagrant = pwd.getpwnam("vagrant")
    remaining = []
    for line in VAGRANT_AUTHORIZED_KEYS.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) < 2 or fields[:2] != [host_key_type, host_key_data]:
            remaining.append(line)
    contents = "\n".join(remaining)
    if contents:
        contents += "\n"
    write_authorized_keys(
        VAGRANT_AUTHORIZED_KEYS,
        contents,
        vagrant.pw_uid,
        vagrant.pw_gid,
    )


def main() -> None:
    if not JUMP_KEY.is_file() or not HOST_KEY.is_file():
        raise SystemExit("Bastion jump and host public keys must both be provided.")
    jump_key_type, jump_key_data = read_key(JUMP_KEY)
    host_key_type, host_key_data = read_key(HOST_KEY)
    account = ensure_jump_user()
    install_jump_key(account, jump_key_type, jump_key_data)
    remove_vagrant_host_key(host_key_type, host_key_data)
    JUMP_KEY.unlink()
    HOST_KEY.unlink()
    print("Bastion forwarding is restricted to internal VM SSH; interactive access is disabled.")


if __name__ == "__main__":
    main()

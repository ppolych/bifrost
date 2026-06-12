import os
import shlex

import paramiko

from core.ssh_credentials import SshCredentials


def proxy_socket(creds: SshCredentials):
    if creds.proxy_command:
        command = creds.proxy_command.replace("%h", creds.host).replace("%p", str(creds.port))
        return paramiko.proxy.ProxyCommand(command)
    if creds.proxy_jump:
        jump = parse_proxy_jump(creds.proxy_jump)
        if jump is None:
            raise paramiko.SSHException(f"Invalid ProxyJump: {creds.proxy_jump!r}")
        user, host, port = jump
        destination = f"{creds.host}:{creds.port}"
        target = f"{user}@{host}" if user else host
        command = f"ssh -W {shlex.quote(destination)} -p {port} {shlex.quote(target)}"
        return paramiko.proxy.ProxyCommand(command)
    return None


def parse_proxy_jump(value: str) -> tuple[str, str, int] | None:
    raw = (value or "").strip()
    if not raw:
        return None
    user = ""
    if "@" in raw:
        user, raw = raw.split("@", 1)
    host, sep, port_text = raw.rpartition(":")
    if not sep:
        host = raw
        port = 22
    else:
        try:
            port = int(port_text)
        except ValueError:
            return None
    if not host or port < 1 or port > 65535:
        return None
    return user, host, port


def load_private_key_with_certificate(creds: SshCredentials) -> paramiko.PKey:
    key_path = os.path.expanduser(creds.key_filename or "")
    cert_path = os.path.expanduser(creds.certificate_filename or "")
    errors: list[BaseException] = []
    for key_cls in (paramiko.RSAKey, paramiko.ECDSAKey, paramiko.Ed25519Key):
        try:
            key = key_cls.from_private_key_file(key_path, password=creds.passphrase)
            key.load_certificate(cert_path)
            return key
        except (OSError, paramiko.SSHException) as e:
            errors.append(e)
    detail = errors[-1] if errors else "unknown key type"
    raise paramiko.SSHException(f"Could not load private key certificate pair: {detail}")

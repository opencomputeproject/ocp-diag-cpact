"""Helpers for creating SSH clients with verified server host keys."""

from typing import Optional

import paramiko


class UnknownHostKeyError(paramiko.SSHException):
    """Raised when the server's host key is not present in any known_hosts file."""


class _RejectUnknownHostPolicy(paramiko.RejectPolicy):
    def missing_host_key(self, client, hostname, key):
        raise UnknownHostKeyError(
            f"Host key for {hostname} ({key.get_name()} {key.fingerprint}) "
            "is not in known_hosts. Verify the key out-of-band and add it to "
            "~/.ssh/known_hosts or the connection's known_hosts_file."
        )


# Host-key verification failures are permanent; never retry them.
HOST_KEY_ERRORS = (UnknownHostKeyError, paramiko.BadHostKeyException)


def create_ssh_client(known_hosts_path: Optional[str] = None) -> paramiko.SSHClient:
    """Return an SSHClient that trusts only already-provisioned host keys.

    Keys are loaded from the user's known_hosts (and ``known_hosts_path`` if
    given). Unknown hosts are rejected with ``UnknownHostKeyError`` (an
    ``paramiko.SSHException``) and changed keys with
    ``paramiko.BadHostKeyException`` instead of being auto-trusted.
    """
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    if known_hosts_path:
        client.load_host_keys(known_hosts_path)
    client.set_missing_host_key_policy(_RejectUnknownHostPolicy())
    return client


_PREFERRED_KEY_TYPES = (
    "ssh-ed25519",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "ssh-rsa",
)


def load_known_host_key(
    hostname: str, port: int = 22, known_hosts_path: Optional[str] = None
) -> paramiko.PKey:
    """Return the trusted host key for ``hostname:port`` from known_hosts.

    Uses the same sources and lookup format as :func:`create_ssh_client`
    (``~/.ssh/known_hosts`` plus ``known_hosts_path``; ``[host]:port`` for
    non-standard ports). Intended for transports that take an expected host
    key directly, such as ``sshtunnel.SSHTunnelForwarder(ssh_host_key=...)``.

    Raises ``UnknownHostKeyError`` if no key is provisioned for the host.
    """
    host_keys = paramiko.HostKeys()
    system_path = os.path.expanduser(os.path.join("~", ".ssh", "known_hosts"))
    if os.path.exists(system_path):
        host_keys.load(system_path)
    if known_hosts_path:
        host_keys.load(known_hosts_path)

    lookup_name = hostname if int(port) == 22 else f"[{hostname}]:{port}"
    entry = host_keys.lookup(lookup_name)
    if not entry:
        raise UnknownHostKeyError(
            f"Host key for {lookup_name} is not in known_hosts. Verify the key "
            "out-of-band and add it to ~/.ssh/known_hosts or the configured "
            "known_hosts file."
        )
    for key_type in _PREFERRED_KEY_TYPES:
        if key_type in entry:
            return entry[key_type]
    return next(iter(entry.values()))

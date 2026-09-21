"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
ConnectionConfig centralizes the parsing of a per-connection configuration
dictionary. Previously every connection class re-implemented the same
``if "inband_host" in config: ... elif "rackmanager_host" in config: ...``
ladders for host / port / username / password. That duplication is the single
biggest source of drift and bugs in this module (a key added to one class is
silently missing from the others).

This class resolves everything once, from a single ``<prefix>_<field>`` naming
convention, where ``<prefix>`` is derived from the connection section name
(``Inband`` -> ``inband``, ``RackManager`` -> ``rackmanager``,
``NodeManager`` -> ``nodemanager``). It also resolves the new privilege-mode
fields (sudo / su passwords, privilege_mode) and the retry policy.

The class is intentionally a thin, Pythonic data holder — no framework, no
registry, no inheritance. It reads the same keys the old code read, so it is a
drop-in behind the existing ``_get_host`` / ``_get_ssh_port`` / ... helpers.
===============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List


# Known section prefixes, in the historical precedence order the old code used.
_KNOWN_PREFIXES: List[str] = ["inband", "rackmanager", "nodemanager"]

# Valid privilege modes.
PRIVILEGE_NONE = "none"
PRIVILEGE_SUDO = "sudo"
PRIVILEGE_SU = "su"
_VALID_PRIVILEGE_MODES = {PRIVILEGE_NONE, PRIVILEGE_SUDO, PRIVILEGE_SU}


@dataclass
class RetryPolicy:
    """Retry configuration for connect / tunnel operations."""

    retry_count: int = 3
    retry_delay: float = 5.0

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "RetryPolicy":
        if not config:
            return cls()
        return cls(
            retry_count=int(config.get("retry_count", 3)),
            retry_delay=float(config.get("retry_delay", 5)),
        )


@dataclass
class ConnectionConfig:
    """
    Strongly-typed view over a single connection's config dict.

    Build it with :meth:`from_dict`. All accessors below are plain attributes
    resolved at construction time, so callers never touch raw keys again.
    """

    raw: Dict[str, Any] = field(default_factory=dict)
    prefix: str = ""

    host: str = ""
    ssh_port: int = 22
    redfish_port: int = 443
    username: str = ""
    password: str = ""

    # Privilege escalation
    privilege_mode: str = PRIVILEGE_NONE
    sudo_password: str = ""
    su_password: str = ""
    # Whether the sudo/su password came from its own config key (True) or fell
    # back to the login password (False). Used only for a redacted log line so
    # operators can see whether their *_sudo_password key was picked up.
    sudo_password_explicit: bool = False
    su_password_explicit: bool = False

    # Tunnel flag (NodeManager only, historically)
    tunnel_enabled: bool = False

    retry: RetryPolicy = field(default_factory=RetryPolicy)

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    @classmethod
    def from_dict(
        cls, config: Optional[Dict[str, Any]], name: Optional[str] = None
    ) -> "ConnectionConfig":
        """
        Build a ConnectionConfig from a per-connection config dict.

        Args:
            config: the ``self.config`` dict passed to a connection today.
            name:   optional section name (e.g. "NodeManager"). If omitted the
                    prefix is inferred from the keys present.
        """
        config = config or {}
        prefix = cls._resolve_prefix(config, name)

        def g(field_name: str, default: Any = None) -> Any:
            """Prefixed key first, then bare key fallback (old behaviour)."""
            if prefix and f"{prefix}_{field_name}" in config:
                return config[f"{prefix}_{field_name}"]
            return config.get(field_name, default)

        privilege_mode = str(g("privilege_mode", PRIVILEGE_NONE) or PRIVILEGE_NONE).lower()
        if privilege_mode not in _VALID_PRIVILEGE_MODES:
            privilege_mode = PRIVILEGE_NONE

        password = g("password", "") or ""
        # sudo/su passwords fall back to the login password when unset, which is
        # the common single-password case. Track whether each was explicitly
        # provided so we can log the source (never the value).
        raw_sudo = g("sudo_password", "") or ""
        raw_su = g("su_password", "") or ""
        sudo_password = raw_sudo or password
        su_password = raw_su or password

        return cls(
            raw=config,
            prefix=prefix,
            host=g("host", "") or "",
            ssh_port=int(g("ssh_port", 22) or 22),
            redfish_port=int(g("redfish_port", 443) or 443),
            username=g("username", "") or "",
            password=password,
            privilege_mode=privilege_mode,
            sudo_password=sudo_password,
            su_password=su_password,
            sudo_password_explicit=bool(raw_sudo),
            su_password_explicit=bool(raw_su),
            tunnel_enabled=bool(config.get(f"{prefix}_tunnel", False)) if prefix else False,
            retry=RetryPolicy.from_config(config),
        )

    @staticmethod
    def _resolve_prefix(config: Dict[str, Any], name: Optional[str]) -> str:
        """Determine the ``<prefix>`` for this section."""
        if name:
            candidate = name.lower()
            if candidate in _KNOWN_PREFIXES:
                return candidate
        # Infer from keys, preserving the old precedence (inband > rack > node).
        for prefix in _KNOWN_PREFIXES:
            if any(k.startswith(f"{prefix}_") for k in config):
                return prefix
        return ""

    # ------------------------------------------------------------------ #
    # Privilege helpers
    # ------------------------------------------------------------------ #
    def privilege_password(self, mode: Optional[str] = None) -> str:
        """Password to feed the escalation prompt for the given/default mode."""
        mode = (mode or self.privilege_mode or PRIVILEGE_NONE).lower()
        if mode == PRIVILEGE_SU:
            return self.su_password
        if mode == PRIVILEGE_SUDO:
            return self.sudo_password
        return ""

    def privilege_password_source(self, mode: Optional[str] = None) -> str:
        """
        Describe where the escalation password came from, for a redacted log
        line. Returns 'configured' (its own *_sudo_password / *_su_password key),
        'login-fallback' (reused the SSH login password), or 'none'.
        """
        mode = (mode or self.privilege_mode or PRIVILEGE_NONE).lower()
        if mode == PRIVILEGE_SU:
            return "configured" if self.su_password_explicit else (
                "login-fallback" if self.su_password else "none"
            )
        if mode == PRIVILEGE_SUDO:
            return "configured" if self.sudo_password_explicit else (
                "login-fallback" if self.sudo_password else "none"
            )
        return "none"

    def __repr__(self) -> str:  # never leak secrets in logs/reprs
        return (
            f"ConnectionConfig(prefix={self.prefix!r}, host={self.host!r}, "
            f"ssh_port={self.ssh_port}, username={self.username!r}, "
            f"privilege_mode={self.privilege_mode!r}, tunnel={self.tunnel_enabled}, "
            f"password=***, sudo_password=***, su_password=***)"
        )


@dataclass
class TunnelAgentConfig:
    """
    Resolved SSH-tunnel *agent* (jump host) credentials.

    This fixes the reported ``No password or public key available`` failure.
    The old code only knew how to look the agent up indirectly via
    ``nodemanager_tunnel_agent`` naming another config section, and the Redfish
    tunnel additionally (and incorrectly) used that *section name* as a
    hostname. Here we resolve, in priority order:

      1. Explicit agent creds on the tunnel section:
         ``tunnel_agent_host`` / ``tunnel_agent_username`` /
         ``tunnel_agent_password`` / ``tunnel_agent_ssh_port``.
      2. Legacy indirection: ``nodemanager_tunnel_agent`` -> a section in the
         global config, read as ``<agent>_host`` / ``<agent>_username`` / ...

    Agent credentials are therefore never assumed to equal NodeManager
    credentials.
    """

    host: str = ""
    username: str = ""
    password: str = ""
    ssh_port: int = 22

    local_host: str = "localhost"
    ssh_local_port: int = 2222
    redfish_local_port: int = 8443

    keepalive: int = 30
    valid: bool = False
    source: str = "none"

    @classmethod
    def from_config(
        cls,
        tunnel_config: Optional[Dict[str, Any]],
        global_config: Optional[Dict[str, Any]] = None,
    ) -> "TunnelAgentConfig":
        tunnel_config = tunnel_config or {}
        global_config = global_config or {}

        local_host = tunnel_config.get("nodemanager_tunnel_local_host", "localhost")
        ssh_local_port = int(tunnel_config.get("nodemanager_tunnel_ssh_local_port", 2222))
        redfish_local_port = int(
            tunnel_config.get("nodemanager_tunnel_redfish_local_port", 8443)
        )
        keepalive = int(tunnel_config.get("nodemanager_tunnel_keepalive", 30))

        # 1) Explicit agent credentials on the tunnel section (preferred).
        host = tunnel_config.get("tunnel_agent_host", "")
        username = tunnel_config.get("tunnel_agent_username", "")
        password = tunnel_config.get("tunnel_agent_password", "")
        ssh_port = int(tunnel_config.get("tunnel_agent_ssh_port", 22))
        source = "explicit"

        # 2) Legacy indirection through a named global section.
        if not host:
            agent = tunnel_config.get("nodemanager_tunnel_agent", "")
            if agent and agent in global_config:
                section = global_config.get(agent, {}) or {}
                a = agent.lower()
                host = section.get(f"{a}_host", "") or section.get("host", "")
                username = section.get(f"{a}_username", "") or section.get("username", "")
                password = section.get(f"{a}_password", "") or section.get("password", "")
                ssh_port = int(section.get(f"{a}_ssh_port", section.get("ssh_port", 22)))
                source = f"legacy_section:{agent}"

        return cls(
            host=host,
            username=username,
            password=password,
            ssh_port=ssh_port,
            local_host=local_host,
            ssh_local_port=ssh_local_port,
            redfish_local_port=redfish_local_port,
            keepalive=keepalive,
            valid=bool(host and username and password),
            source=source,
        )

    def missing(self) -> List[str]:
        """Which required agent fields are empty (for actionable errors)."""
        gaps = []
        if not self.host:
            gaps.append("agent host")
        if not self.username:
            gaps.append("agent username")
        if not self.password:
            gaps.append("agent password")
        return gaps

    def __repr__(self) -> str:
        return (
            f"TunnelAgentConfig(host={self.host!r}, username={self.username!r}, "
            f"ssh_port={self.ssh_port}, source={self.source!r}, valid={self.valid}, "
            f"password=***)"
        )

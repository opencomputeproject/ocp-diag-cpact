"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

This source code is licensed under the MIT license found in the
LICENSE file in the root directory of this source tree.

===============================================================================
Interactive privilege escalation for SSH.

The existing SSHConnection runs everything through ``exec_command`` (a fresh,
non-interactive channel per command). That cannot drive an interactive
``sudo`` / ``su`` password prompt, and it cannot keep an elevated shell alive
across multiple commands. This module adds a small state machine over a single
paramiko *shell* channel (``invoke_shell`` / ``get_pty``) that can:

  * open an interactive PTY shell,
  * run ``sudo -i`` / ``sudo su -`` / ``su -`` and answer the password prompt,
  * verify the shell is actually elevated (``id -u`` == 0),
  * run subsequent commands inside the elevated shell without re-authenticating,
  * capture stdout/stderr and the exit code of each command,
  * exit the elevated shell (and the login shell) cleanly.

Design notes
------------
* Output framing: after each command we emit a unique sentinel that also
  carries the exit status: ``echo <MARKER>:$?``. We read until we see the
  marker, which unambiguously delimits one command's output and gives us its
  return code, even for commands that print no trailing newline.
* Prompt detection: a permissive regex matches ``[sudo] password for user:`` and
  bare ``Password:`` prompts. If escalation needs no password (passwordless
  sudo / already root) we detect elevation directly and skip sending one.
* Secrets: the password is only ever written to the channel. It is never
  logged, echoed back into captured output (the prompt line is stripped), or
  placed in exceptions.
* The channel object is duck-typed. Anything exposing ``send``, ``recv``,
  ``recv_ready``, ``settimeout`` and ``close`` works, which is what makes this
  unit-testable without a live SSH server.
===============================================================================
"""

from __future__ import annotations

import re
import socket
import time
import uuid
from typing import Optional, Tuple


# Password-prompt patterns (case-insensitive, matched against a decoded tail).
_PROMPT_RE = re.compile(r"(?:\[sudo\]\s*)?password[^:\n]*:\s*$", re.IGNORECASE)

# sudo's failure line after a bad password.
_SUDO_FAIL_RE = re.compile(r"(sorry, try again|authentication failure|incorrect password)", re.IGNORECASE)

# su's failure line.
_SU_FAIL_RE = re.compile(r"(su:\s*authentication failure|incorrect password)", re.IGNORECASE)

# Escalation command per mode.
ESCALATION_COMMANDS = {
    "sudo": "sudo -i",
    "su": "su -",
    "sudo_su": "sudo su -",
}


class PrivilegeEscalationError(Exception):
    """Raised when the shell cannot be elevated (bad password, no prompt, etc.)."""


class PrivilegedShell:
    """
    Drives an interactive shell channel through privilege escalation and
    command execution. One instance wraps one live channel.
    """

    def __init__(
        self,
        channel,
        password: str,
        logger,
        prompt_timeout: float = 15.0,
        command_timeout: float = 60.0,
        encoding: str = "utf-8",
    ) -> None:
        self._chan = channel
        self._password = password or ""
        self._log = logger
        self._prompt_timeout = prompt_timeout
        self._command_timeout = command_timeout
        self._encoding = encoding
        self._marker_prefix = f"__CPACT_{uuid.uuid4().hex[:12]}__"
        self._elevated = False
        self._transcript = ""  # redacted rolling capture of what the shell sent
        try:
            self._chan.settimeout(1.0)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Diagnostics
    # ------------------------------------------------------------------ #
    def _redact(self, text: str) -> str:
        """Scrub the password out of any text before it is logged or surfaced."""
        if self._password:
            text = text.replace(self._password, "***")
        return text

    def diagnostics(self, tail: int = 500) -> str:
        """Return a redacted tail of the shell transcript for troubleshooting."""
        return self._redact(self._transcript)[-tail:]

    # ------------------------------------------------------------------ #
    # Low-level IO
    # ------------------------------------------------------------------ #
    def _read_until(self, predicate, timeout: float) -> str:
        """
        Accumulate decoded output until ``predicate(buffer)`` is truthy or timeout.

        Uses a plain blocking ``recv`` (bounded by the channel's socket timeout)
        rather than gating on ``recv_ready()``. On a real paramiko channel
        ``recv_ready()`` is racy immediately after a ``send`` — it can report no
        data for a beat even though the shell is about to reply — which made the
        old poll loop miss output and time out. A blocking recv that tolerates
        ``socket.timeout`` is the idiomatic, reliable pattern and still works
        with the in-memory test fakes (which return ``b""`` when empty).
        """
        deadline = time.time() + timeout
        buf = ""
        while time.time() < deadline:
            got = False
            remaining = deadline - time.time()
            # Bound this recv to the time we have left (never longer), so a drain
            # with a short deadline can't block for the full socket timeout.
            try:
                self._chan.settimeout(max(0.05, min(remaining, 0.5)))
            except Exception:
                pass
            try:
                chunk = self._chan.recv(4096)
                if chunk:
                    decoded = chunk.decode(self._encoding, errors="ignore")
                    buf += decoded
                    self._transcript += decoded
                    got = True
                elif self._channel_closed():
                    # EOF on a closed channel: nothing more will ever arrive.
                    return buf
            except socket.timeout:
                pass
            except Exception:
                # transient read error / closed channel — keep polling until the
                # deadline, then return what we have.
                if self._channel_closed():
                    return buf
            if predicate(buf):
                return buf
            if not got:
                time.sleep(0.02)
        return buf

    def _channel_closed(self) -> bool:
        """True once the channel is closed or the remote end sent EOF."""
        return bool(
            getattr(self._chan, "closed", False)
            or getattr(self._chan, "eof_received", False)
        )

    def _send_line(self, text: str) -> None:
        self._chan.send((text + "\n").encode(self._encoding))

    def _send_secret_line(self, secret: str) -> None:
        # Same as _send_line but this one we promise never to log.
        self._chan.send((secret + "\n").encode(self._encoding))

    # ------------------------------------------------------------------ #
    # Escalation
    # ------------------------------------------------------------------ #
    def escalate(self, mode: str) -> bool:
        """
        Escalate the shell using the given mode: ``sudo``, ``su`` or ``sudo_su``.

        Returns True on success, raises PrivilegeEscalationError on failure.
        """
        escalation_cmd = ESCALATION_COMMANDS.get(mode)
        if escalation_cmd is None:
            raise PrivilegeEscalationError(f"Unknown privilege mode: {mode}")

        self._log.info(f"Escalating privileges via '{escalation_cmd}'")

        # Drain any login banner already sitting in the buffer.
        self._read_until(lambda b: False, timeout=0.2)

        self._send_line(escalation_cmd)

        def prompt_or_settled(b: str) -> bool:
            tail = b[-200:]
            return bool(_PROMPT_RE.search(tail)) or bool(
                _SUDO_FAIL_RE.search(b) or _SU_FAIL_RE.search(b)
            )

        out = self._read_until(prompt_or_settled, timeout=self._prompt_timeout)

        if _SUDO_FAIL_RE.search(out) or _SU_FAIL_RE.search(out):
            raise PrivilegeEscalationError("privilege escalation refused before password")

        if _PROMPT_RE.search(out[-200:]):
            if not self._password:
                raise PrivilegeEscalationError(
                    "password prompt received but no privilege password configured"
                )
            self._send_secret_line(self._password)
            # After sending the password, wait for either an explicit failure
            # line, a *repeated* password prompt (wrong password / retry), or the
            # shell to settle. We confirm via _verify_elevated below regardless.
            def failed_or_reprompt(b: str) -> bool:
                tail = b[-200:]
                return bool(
                    _SUDO_FAIL_RE.search(b)
                    or _SU_FAIL_RE.search(b)
                    or _PROMPT_RE.search(tail)
                )

            settle = self._read_until(failed_or_reprompt, timeout=1.5)
            if _SUDO_FAIL_RE.search(settle) or _SU_FAIL_RE.search(settle):
                raise PrivilegeEscalationError("privilege escalation failed: bad password")
            if _PROMPT_RE.search(settle[-200:]):
                # sudo/su is still asking for a password: the one we sent was not
                # accepted (wrong secret, or a different account's password is
                # required for this mode).
                raise PrivilegeEscalationError(
                    "privilege escalation failed: password not accepted "
                    "(shell is still prompting for a password)"
                )
        else:
            self._log.info("No password prompt detected; assuming passwordless escalation")

        if not self._verify_elevated():
            hint = self._redact(self._transcript)[-400:].strip()
            self._log.error(
                "Privilege escalation could not be confirmed as root. "
                "Last shell output (password redacted):\n%s", hint
            )
            raise PrivilegeEscalationError(
                "privilege escalation did not result in a root shell; "
                "see log for the shell transcript tail"
            )

        self._elevated = True
        self._log.info("Privilege escalation successful (uid 0 confirmed)")
        return True

    def _verify_elevated(self) -> bool:
        """
        Confirm the shell is root by checking ``id -u`` == 0.

        A freshly-started root login shell (``sudo -i`` / ``su -``) may still be
        emitting its profile/MOTD when we first ask, so we try a couple of times
        with a short drain in between before giving up.
        """
        for attempt in range(3):
            stdout, code = self.run("id -u", timeout=self._prompt_timeout)
            if stdout.strip() == "0":
                return True
            # Drain any late banner output, then retry.
            self._read_until(lambda b: False, timeout=0.3)
        return False

    # ------------------------------------------------------------------ #
    # Command execution inside the (possibly elevated) shell
    # ------------------------------------------------------------------ #
    def run(self, command: str, timeout: Optional[float] = None) -> Tuple[str, int]:
        """
        Run ``command`` in the shell and return ``(stdout, exit_code)``.

        stderr is redirected into stdout inside the shell (interactive shells do
        not cleanly separate the two); callers that need separation should use
        the non-interactive path. The command's real exit code is captured via
        the marker.
        """
        timeout = timeout or self._command_timeout
        marker = f"{self._marker_prefix}{uuid.uuid4().hex[:8]}"
        # Emit marker + exit code on its own line after the command runs.
        wrapped = f"{command}; echo {marker}:$?"
        self._send_line(wrapped)

        marker_re = re.compile(re.escape(marker) + r":(\-?\d+)")

        out = self._read_until(lambda b: bool(marker_re.search(b)), timeout=timeout)
        match = marker_re.search(out)
        if not match:
            self._log.warning(
                "Command marker not found before timeout. Last shell output "
                "(password redacted):\n%s", self._redact(out)[-400:].strip()
            )
            # Stop the command so the (shared) shell is usable again; this is a
            # PTY, so Ctrl+C really interrupts the foreground job.
            self.interrupt()
            return self._strip_echo(out, wrapped, marker), -1

        exit_code = int(match.group(1))
        body = out[: match.start()]
        return self._strip_echo(body, wrapped, marker), exit_code

    def interrupt(self, resync_timeout: float = 5.0) -> bool:
        """
        Send Ctrl+C to the foreground command and wait for the shell to accept
        commands again. Returns True if the shell answered a resync marker.
        """
        if self._channel_closed():
            return False
        try:
            self._chan.send(b"\x03")
        except Exception:
            return False
        self._read_until(lambda b: False, timeout=0.3)
        # The PTY echoes our input, so wait for text only execution can produce.
        resync = f"{self._marker_prefix}resync_{uuid.uuid4().hex[:8]}"
        try:
            self._send_line(f"echo {resync}_$((40+2))")
        except Exception:
            return False
        out = self._read_until(lambda b: f"{resync}_42" in b, timeout=resync_timeout)
        ok = f"{resync}_42" in out
        if not ok:
            self._log.warning("Shell did not respond after interrupting a timed-out command")
        return ok

    def _strip_echo(self, text: str, wrapped_cmd: str, marker: str) -> str:
        """
        Remove the echoed command line and any trailing prompt fragments so the
        caller sees only real command output.
        """
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                cleaned.append(line)
                continue
            # Drop the PTY echo of the command we sent.
            if wrapped_cmd in line or (marker in line and "echo" in line):
                continue
            cleaned.append(line)
        result = "\n".join(cleaned).strip("\n")
        return result

    # ------------------------------------------------------------------ #
    # Teardown
    # ------------------------------------------------------------------ #
    def deescalate(self) -> None:
        """Exit the elevated shell layer (leaving the login shell intact)."""
        if self._elevated:
            self._best_effort_exit()
            self._elevated = False

    def _best_effort_exit(self) -> None:
        """
        Send a single 'exit' without ever blocking. Interactive ``send`` can
        block when the remote pty isn't reading, so we use a short send timeout
        and swallow anything that goes wrong — teardown must not hang.
        """
        try:
            self._chan.settimeout(0.3)
        except Exception:
            pass
        try:
            self._chan.send(b"exit\n")
        except Exception:
            pass
        # Tiny, bounded drain so a clean exit is acknowledged; never required.
        self._read_until(lambda b: False, timeout=0.15)

    def close(self) -> None:
        """Exit everything and force the channel closed. Never blocks."""
        try:
            if self._elevated:
                self._best_effort_exit()   # leave the root shell
                self._elevated = False
            self._best_effort_exit()       # leave the login shell
        except Exception:
            pass
        # Force the channel down regardless of shell state. shutdown() unblocks
        # any pending send/recv; close() releases it.
        for method in ("shutdown", "close"):
            fn = getattr(self._chan, method, None)
            if fn is None:
                continue
            try:
                if method == "shutdown":
                    fn(2)  # SHUT_RDWR
                else:
                    fn()
            except Exception:
                pass

    @property
    def elevated(self) -> bool:
        return self._elevated

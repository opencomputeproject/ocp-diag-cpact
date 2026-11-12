"""
Copyright (c) 2025 Open Compute Project
Licensed under the MIT License.

Small, dependency-free retry helper. Deliberately not a decorator framework —
just a function that retries a callable a configurable number of times with a
fixed delay, logging each attempt. Used for SSH connect, Redfish connect and
tunnel creation.
"""

from __future__ import annotations

import time
from typing import Callable, Optional, Tuple, Type, TypeVar

T = TypeVar("T")


def retry_call(
    func: Callable[[], T],
    *,
    retries: int = 3,
    delay: float = 5.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
    logger=None,
    description: str = "operation",
    success_predicate: Optional[Callable[[T], bool]] = None,
    give_up_on: Tuple[Type[BaseException], ...] = (),
) -> T:
    """
    Call ``func`` up to ``retries`` times.

    A "failure" is either a raised exception in ``exceptions`` OR a return value
    that fails ``success_predicate`` (when provided). This lets us retry
    functions that signal failure by returning ``False`` (like ``connect()``)
    as well as ones that raise.

    Exceptions in ``give_up_on`` are re-raised immediately without retrying,
    even if they also match ``exceptions``.

    Returns the last result. Re-raises the last exception only if every attempt
    raised.
    """
    attempt = 0
    last_exc: Optional[BaseException] = None
    last_result: Optional[T] = None

    while attempt < max(1, retries):
        attempt += 1
        try:
            result = func()
            if success_predicate is None or success_predicate(result):
                if attempt > 1 and logger:
                    logger.info(f"{description} succeeded on attempt {attempt}")
                return result
            last_result = result
            if logger:
                logger.warning(
                    f"{description} attempt {attempt}/{retries} did not succeed"
                )
        except exceptions as exc:  # noqa: B902 - intentional broad-ish catch
            if give_up_on and isinstance(exc, give_up_on):
                raise
            last_exc = exc
            if logger:
                logger.warning(
                    f"{description} attempt {attempt}/{retries} failed: {exc}"
                )

        if attempt < retries:
            time.sleep(delay)

    if last_result is not None:
        return last_result
    if last_exc is not None:
        raise last_exc
    return last_result  # type: ignore[return-value]

import copy
import logging
import os
import re
from typing import Dict, List, Optional, Tuple, Any

_LOGGER = logging.getLogger(__name__)
_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")
_PARAM_PREFIX = "param:"
_PARAM_SEP_RE = re.compile(r"\s*(?:->|\.)\s*")
_PARAM_SCALAR_TYPES = (str, int, float, bool)


class PathResolutionError(Exception):
    pass


# Normalize env variable names for cross-platform support
WINDOWS_ENV_MAP = {
    "HOME": "USERPROFILE",
    "APPDATA": "APPDATA",
}

LINUX_ENV_MAP = {
    "USERPROFILE": "HOME",
}


def _normalize_env_name(var: str) -> str:
    """
    Convert env names between platforms:
    - On Windows, HOME → USERPROFILE (if HOME is not set)
    - On Linux/macOS, USERPROFILE → HOME (if USERPROFILE is not set)
    """

    # Windows
    if os.name == "nt":
        if var in WINDOWS_ENV_MAP:
            alt = WINDOWS_ENV_MAP[var]
            if alt in os.environ:
                return alt

    # Linux / macOS
    else:
        if var in LINUX_ENV_MAP:
            alt = LINUX_ENV_MAP[var]
            if alt in os.environ:
                return alt

    return var


def _resolve_env_var(token: str) -> Optional[str]:
    """
    Handles:
      {env:VAR}
      {env:%VAR%}
    Cross-platform normalization.
    """

    var = token[4:]

    # Windows style: %APPDATA%
    if var.startswith("%") and var.endswith("%"):
        var = var[1:-1]  # remove % %

    var = _normalize_env_name(var)

    return os.environ.get(var)


def _param_to_str(val: Any) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    return str(val)


def _split_param_ref(ref: str) -> Optional[Tuple[str, ...]]:
    """Split `server.ip` / `server->ip` / `a.b->c` into key segments."""
    parts = tuple(_PARAM_SEP_RE.split(ref.strip()))
    if not parts or any(not p for p in parts):
        return None
    return parts


class _ParamResolver:
    """
    Resolves `parameters` entries on demand, so a param may reference env vars, paths
    and other parameters (including nested ones) regardless of declaration order.
    Circular references and unsupported value types are reported, not raised.
    """

    def __init__(
        self,
        raw_params: Dict[str, Any],
        paths: Dict[str, Any],
        unresolved_acc: List[Dict[str, str]],
    ):
        self._raw = raw_params
        self._paths = paths
        self._acc = unresolved_acc
        self._cache: Dict[Tuple[str, ...], Any] = {}
        self._in_progress = set()

    def __bool__(self):
        return bool(self._raw)

    def has(self, ref: str) -> bool:
        parts = _split_param_ref(ref)
        return bool(parts) and parts[0] in self._raw

    def lookup(self, ref: str) -> Optional[Any]:
        parts = _split_param_ref(ref)
        if not parts:
            return None
        return self._resolve(parts)

    def _report(self, parts: Tuple[str, ...], problem: str):
        name = ".".join(parts)
        self._acc.append(
            {
                "placeholder": f"{_PARAM_PREFIX}{name}",
                "context": f"parameters.{name}",
                "reason": f"parameters[{name}] {problem}",
            }
        )

    def _resolve(self, parts: Tuple[str, ...]) -> Optional[Any]:
        if parts in self._cache:
            return self._cache[parts]

        node: Any = self._raw
        for key in parts:
            if not isinstance(node, dict) or key not in node:
                return None
            node = node[key]

        if parts in self._in_progress:
            self._report(parts, "has a circular reference")
            return None

        if isinstance(node, dict):
            self._in_progress.add(parts)
            out = {}
            for key, raw_child in node.items():
                child = self._resolve(parts + (key,))
                out[key] = raw_child if child is None else child
            self._in_progress.discard(parts)
        elif isinstance(node, str):
            self._in_progress.add(parts)
            out, _ = _replace_placeholders_in_string(
                node, self._paths, self._acc, "parameters." + ".".join(parts), self
            )
            self._in_progress.discard(parts)
        elif isinstance(node, _PARAM_SCALAR_TYPES):
            out = node
        else:
            self._report(parts, "must be a string, number, boolean or group")
            return None

        self._cache[parts] = out
        return out


def _resolve_placeholder(
    token: str, paths: Dict[str, Any], params_: Optional[_ParamResolver] = None
) -> Tuple[Optional[Any], str, bool]:
    # Environment placeholder
    if token.startswith("env:"):
        val = _resolve_env_var(token)
        return val, f"env:{token[4:]}", True  # env vars are required now

    # Explicit param placeholder: {param:name}, {param:group.key}, {param:group->key}
    if token.startswith(_PARAM_PREFIX):
        ref = token[len(_PARAM_PREFIX):].strip()
        val = params_.lookup(ref) if params_ else None
        return val, f"parameters[{ref}]", True

    val = paths.get(token)
    if isinstance(val, str):
        return val, f"paths[{token}]", True

    # Bare {name} falls back to parameters (param names never collide with paths)
    if params_ and params_.has(token):
        return params_.lookup(token), f"parameters[{token}]", True

    reason = f"paths/parameters[{token}]" if params_ else f"paths[{token}]"
    return None, reason, True


def _replace_placeholders_in_string(
    s: str,
    paths: Dict[str, Any],
    unresolved_acc: List[Dict[str, str]],
    context: str,
    params_: Optional[_ParamResolver] = None,
) -> Tuple[Any, int]:

    # A string that is exactly one param placeholder keeps the param's native
    # type (number/boolean/group) instead of being stringified.
    whole = _PLACEHOLDER_RE.fullmatch(s.strip()) if params_ else None
    if whole:
        val, _, _ = _resolve_placeholder(whole.group(1).strip(), paths, params_)
        if val is not None and not isinstance(val, str):
            return copy.deepcopy(val), 1

    resolved_count = 0

    def repl(m):
        nonlocal resolved_count
        token = m.group(1).strip()

        val, reason, is_required = _resolve_placeholder(token, paths, params_)

        if isinstance(val, dict):
            val, reason = None, f"{reason} is a group, not a value"

        if val is None:
            unresolved_acc.append(
                {
                    "placeholder": token,
                    "context": context,
                    "reason": reason,
                }
            )
            return m.group(0)

        resolved_count += 1
        return _param_to_str(val)

    result = _PLACEHOLDER_RE.sub(repl, s)
    return result, resolved_count


def _find_block(yaml_data: Dict[str, Any], key: str) -> Any:
    """Look up a recipe block either at this level or under `test_scenario`."""
    if key in yaml_data:
        return yaml_data[key]
    scenario = yaml_data.get("test_scenario")
    if isinstance(scenario, dict):
        return scenario.get(key)
    return None


def resolve_paths_in_yaml(
    yaml_data: Dict[str, Any],
    paths_override: Optional[Dict[str, Any]] = None,
    raise_on_unresolved: bool = False,
):
    paths = paths_override if paths_override else yaml_data.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("'paths' must be a dictionary")

    raw_params = _find_block(yaml_data, "parameters") or {}
    if not isinstance(raw_params, dict):
        raise ValueError("'parameters' must be a dictionary")

    declared_paths = paths or _find_block(yaml_data, "paths") or {}
    if not isinstance(declared_paths, dict):
        declared_paths = {}
    collisions = sorted(set(raw_params) & set(declared_paths))

    report = {"resolved_count": 0, "unresolved": []}

    if collisions:
        # Paths take precedence; colliding parameters are ignored and reported.
        _LOGGER.error(
            "Param names must not duplicate path names (param ignored): %s",
            ", ".join(collisions),
        )
        for name in collisions:
            report["unresolved"].append(
                {
                    "placeholder": f"{_PARAM_PREFIX}{name}",
                    "context": f"parameters.{name}",
                    "reason": f"parameters[{name}] duplicates paths[{name}]",
                }
            )
        raw_params = {k: v for k, v in raw_params.items() if k not in collisions}

    params_ = _ParamResolver(copy.deepcopy(raw_params), paths, report["unresolved"])
    for name in raw_params:
        params_.lookup(name)

    def walk(node: Any, ctx: str):
        if isinstance(node, dict):
            for k, v in list(node.items()):
                node[k] = walk(v, f"{ctx}.{k}")
            return node

        if isinstance(node, list):
            for i, v in enumerate(node):
                node[i] = walk(v, f"{ctx}[{i}]")
            return node

        if isinstance(node, str):
            new_s, count = _replace_placeholders_in_string(
                node, paths, report["unresolved"], ctx, params_
            )
            report["resolved_count"] += count
            return new_s

        return node

    walk(yaml_data, "root")

    # Deduplicate unresolved items
    seen = set()
    uniq = []
    for u in report["unresolved"]:
        t = (u["placeholder"], u["context"], u["reason"])
        if t not in seen:
            seen.add(t)
            uniq.append(u)
    report["unresolved"] = uniq

    if raise_on_unresolved and report["unresolved"]:
        msgs = [
            f"{u['placeholder']} ({u['reason']}) at {u['context']}"
            for u in report["unresolved"]
        ]
        raise PathResolutionError("Unresolved placeholders: " + "; ".join(msgs))
    return yaml_data, report


# if __name__ == "__main__":
#     # Example usage
#     sample_yaml = {
#         "paths": {
#             "data_dir": "/data",
#             "config_file": "{data_dir}/config.yaml",
#             "log_dir": "{env:APPDATA}/logs"
#         },
#         "settings": {
#             "config_path": "{config_file}",
#             "log_path": "{log_dir}/app.log"
#         }
#     }

#     resolved_yaml, report = resolve_paths_in_yaml(sample_yaml, raise_on_unresolved=False)
#     print("Resolved YAML:", resolved_yaml)
#     print("Report:", report)
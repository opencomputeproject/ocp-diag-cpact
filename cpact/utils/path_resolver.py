import os
import re
from typing import Dict, List, Optional, Tuple, Any

_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")

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


def _resolve_placeholder(token: str, paths: Dict[str, Any]) -> Tuple[Optional[str], str, bool]:
    # Environment placeholder
    if token.startswith("env:"):
        val = _resolve_env_var(token)
        return val, f"env:{token[4:]}", True  # env vars are required now

    val = paths.get(token)
    return (val if isinstance(val, str) else None), f"paths[{token}]", True


def _replace_placeholders_in_string(s: str, paths: Dict[str, Any],
                                    unresolved_acc: List[Dict[str, str]],
                                    context: str) -> Tuple[str, int]:

    resolved_count = 0

    def repl(m):
        nonlocal resolved_count
        token = m.group(1).strip()

        val, reason, is_required = _resolve_placeholder(token, paths)

        if val is None:
            unresolved_acc.append({
                "placeholder": token,
                "context": context,
                "reason": reason,
            })
            return m.group(0)

        resolved_count += 1
        return val

    result = _PLACEHOLDER_RE.sub(repl, s)
    return result, resolved_count


def resolve_paths_in_yaml(
    yaml_data: Dict[str, Any],
    paths_override: Optional[Dict[str, Any]] = None,
    raise_on_unresolved: bool = False,
):
    paths = paths_override if paths_override else yaml_data.get("paths", {})
    if not isinstance(paths, dict):
        raise ValueError("'paths' must be a dictionary")

    report = {
        "resolved_count": 0,
        "unresolved": []
    }

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
            new_s, count = _replace_placeholders_in_string(node, paths, report["unresolved"], ctx)
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
        msgs = [f"{u['placeholder']} ({u['reason']}) at {u['context']}" for u in report["unresolved"]]
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
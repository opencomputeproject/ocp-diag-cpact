# CPACT Standalone Packaging

Builds a single-file, self-contained CPACT executable with [PyInstaller](https://pyinstaller.org).
Target systems need **no Python, no pip packages, no setup** — just copy the binary and run it.

## Build

```bash
./packaging/build_executable.sh              # full build (includes scenario-creator GUI)
CPACT_NO_GUI=1 ./packaging/build_executable.sh   # smaller CLI-only build (excludes PyQt5)
```

Output: `dist/cpact`

The script creates an isolated virtualenv under `build/pyinstaller-venv`, installs
`requirements.txt` + PyInstaller, and builds from `packaging/cpact.spec`.

## What's bundled

- The Python interpreter and all dependencies (paramiko, redfish, jsonschema, ocptv, ...)
- `spec/` — all schema versions and default inputs (`score_weights.json`, `config.json`)
- `tests/` — the built-in scenario recipes (override with `--test_dir`)
- Scenario-creator icons

## Deploy & run

```bash
scp dist/cpact user@target:/usr/local/bin/cpact
ssh user@target cpact --list
```

By default the frozen executable:
- discovers scenarios from the bundled `tests/` (use `--test_dir` for your own recipes)
- writes results/logs to a `workspace/` directory next to the executable
  (use `--workspace` to redirect)

## Notes

- **Build per OS/arch**: PyInstaller does not cross-compile. Build on Linux x86_64
  for Linux x86_64 targets, etc.
- **glibc compatibility (Linux)**: the binary requires the target's glibc to be the
  same or newer than the build machine's. Build on the oldest distro you need to
  support (or use a container, e.g. `ubuntu:20.04`). For fully static binaries,
  post-process with [staticx](https://github.com/JonathonReinhart/staticx).
- First launch extracts the bundle to a temp dir, so startup takes a few seconds.

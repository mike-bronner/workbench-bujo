"""Tests for the uv self-heal and dead-interpreter rebuild in
``scribe/bin/launcher.sh``.

The launcher bootstraps the scribe MCP. Two behaviors are guarded here:

  * **uv self-heal** — ``uv`` is a per-machine tool (not synced via iCloud),
    so on a fresh machine or after a toolchain wipe it can be missing while
    every path in the launcher shells out to it. The launcher installs it via
    the official astral script, then re-checks and aborts with an actionable
    error if it's still absent.
  * **dead-interpreter rebuild** — a ``.venv-stable`` carried over from another
    machine can have a *present-but-dead* ``bin/python`` symlink (points at the
    other box's uv-managed interpreter, absent here). It passes the launcher's
    ``-x`` check yet can't run, so the hash guard alone would never rebuild it.

Both live in bash, so — in the same spirit as ``test_session_warmup_drift.py``
does for the warmup hook, though that sibling execs its hook in place while the
launcher self-locates ``SCRIBE_DIR`` from ``BASH_SOURCE`` and so is copied into
a hermetic tree here — these tests drive the real launcher as a subprocess with
stubbed ``uv``/``curl``/``readlink``, asserting observable behavior. stdout is
the MCP stdio channel, so the bootstrap *and* rebuild paths assert it stays
byte-for-byte clean. The ``readlink`` stub rejects ``-f`` like a pre-12.3 macOS
``/usr/bin/readlink``, pinning the dead-interpreter guard to a portable,
readlink-free form (a regression to ``readlink -f`` would wipe a healthy venv
under the stub and fail the healthy-venv test).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
from pathlib import Path

# scribe/tests/ -> scribe/ -> scribe/bin/launcher.sh
LAUNCHER = Path(__file__).resolve().parents[1] / "bin" / "launcher.sh"

# A `uv` stub. Logs on stderr, and — in the venv/pip branches — deliberately
# chatters on *stdout*, modeling a uv whose `--quiet` regressed. The launcher's
# stdout is the MCP stdio channel, so its explicit redirects (`uv venv` and
# `uv pip install` both `>/dev/null`) must swallow this; that is exactly what
# the stdout-clean assertions pin — drop a redirect and they fail. It
# materializes just enough of a venv for the launcher to `exec` the entry
# point and exit 0.
UV_STUB = r"""#!/usr/bin/env bash
set -euo pipefail
echo "uv-stub $*" 1>&2
case "${1:-}" in
  venv)
    # uv venv <dir> --python <spec>
    echo "uv-stub venv chatter (must never reach the launcher's stdout)"
    dir="${2:?uv venv needs a target dir}"
    mkdir -p "${dir}/bin"
    ln -sf "$(command -v python3)" "${dir}/bin/python"
    ;;
  pip)
    echo "uv-stub pip chatter (must never reach the launcher's stdout)"
    # uv pip install --python <venv>/bin/python --quiet --force-reinstall <wheel>
    venvpy=""
    prev=""
    for arg in "$@"; do
      [ "${prev}" = "--python" ] && venvpy="${arg}"
      prev="${arg}"
    done
    bindir="$(dirname "${venvpy}")"
    printf '#!/bin/sh\nexit 0\n' > "${bindir}/bujo-scribe-mcp"
    chmod +x "${bindir}/bujo-scribe-mcp"
    ;;
  run)
    # dev-mode / no-wheel fallback
    exit 0
    ;;
esac
"""

# Fake astral installer *download*. Records that it ran (and its full argv, so a
# test can assert the launcher passed the `--connect-timeout`/`--max-time`
# anti-hang flags), then emits (on stdout, which the launcher pipes into
# `sh 1>&2`) a script that installs the uv stub into ~/.local/bin and prints a
# loud marker — proving the launcher redirects every byte of bootstrap output
# away from its own stdout.
CURL_INSTALL_OK = r"""#!/usr/bin/env bash
set -euo pipefail
touch "${CURL_SENTINEL}"
printf '%s\n' "$@" > "${CURL_ARGV}"
cat <<EOF
echo "INSTALLER_STDOUT_MARKER installing uv"
mkdir -p "\$HOME/.local/bin"
install -m 0755 "${UV_STUB_SRC}" "\$HOME/.local/bin/uv"
EOF
"""

# Simulate an offline download: record the attempt (and its argv, as above),
# emit nothing installable, fail fast (no hang). Also used as a "must never run"
# tripwire when uv is already present.
CURL_OFFLINE = r"""#!/usr/bin/env bash
touch "${CURL_SENTINEL}"
printf '%s\n' "$@" > "${CURL_ARGV}"
echo "curl: (6) Could not resolve host: astral.sh" 1>&2
exit 6
"""

# An old-macOS `readlink` (pre-12.3): rejects `-f` the way /usr/bin/readlink
# did before the GNU-style extension landed. On the stub PATH for every test,
# so the dead-interpreter guard is pinned to a portable, readlink-free form:
# with this stub, a regression back to `readlink -f` makes
# `$(readlink -f ... 2>/dev/null)` yield "" and the guard wipes a *healthy*
# venv — failing test_dead_interpreter_guard_noop_when_interpreter_resolves.
READLINK_NO_F = r"""#!/usr/bin/env bash
if [ "${1:-}" = "-f" ]; then
  echo "usage: readlink [-n] [file ...]" 1>&2
  exit 1
fi
exec /usr/bin/readlink "$@"
"""


def _write_exec(path: Path, content: str) -> Path:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _real_python() -> str:
    py = shutil.which("python3") or shutil.which("python")
    assert py, "need a python3 on PATH to build the fixture"
    return py


def _make_scribe(tmp_path: Path) -> Path:
    """Hermetic scribe tree: a copy of the real launcher + a fake wheel.

    Returns the scribe dir; its ``bin/launcher.sh`` is the script under test,
    and all launcher state (``.venv-stable``, ``run/``) stays inside it.
    """
    scribe = tmp_path / "scribe"
    (scribe / "bin").mkdir(parents=True)
    (scribe / "wheels").mkdir(parents=True)
    _write_exec(scribe / "bin" / "launcher.sh", LAUNCHER.read_text())
    (scribe / "wheels" / "bujo_scribe_mcp-0.0.0-py3-none-any.whl").write_bytes(
        b"fake wheel bytes\n"
    )
    return scribe


def _wheel_hash(scribe: Path) -> str:
    wheel = next((scribe / "wheels").glob("bujo_scribe_mcp-*.whl"))
    return hashlib.sha256(wheel.read_bytes()).hexdigest()


def _stubbin(tmp_path: Path, *, uv: bool, curl: str) -> Path:
    """Build a PATH dir with an optional uv stub, a chosen curl stub, and the
    old-macOS readlink stub (portability pin — see READLINK_NO_F)."""
    stubbin = tmp_path / "stubbin"
    stubbin.mkdir(exist_ok=True)
    if uv:
        _write_exec(stubbin / "uv", UV_STUB)
    _write_exec(stubbin / "curl", curl)
    _write_exec(stubbin / "readlink", READLINK_NO_F)
    return stubbin


def _run(scribe: Path, tmp_path: Path, stubbin: Path, extra_env=None):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {
        "HOME": str(home),
        # Real coreutils resolve here; the stub dir shadows uv/curl.
        "PATH": f"{stubbin}:/usr/bin:/bin:/usr/sbin:/sbin",
        "CURL_SENTINEL": str(tmp_path / "curl-ran"),
        "CURL_ARGV": str(tmp_path / "curl-argv"),
    }
    if extra_env:
        env.update(extra_env)
    # timeout guards against a hang on the offline path.
    return subprocess.run(
        ["/bin/bash", str(scribe / "bin" / "launcher.sh")],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_uv_selfheal_is_noop_when_uv_present(tmp_path):
    # uv on PATH -> the installer is never invoked.
    scribe = _make_scribe(tmp_path)
    stubbin = _stubbin(tmp_path, uv=True, curl=CURL_OFFLINE)  # tripwire
    res = _run(scribe, tmp_path, stubbin)
    assert res.returncode == 0, res.stderr
    assert not (tmp_path / "curl-ran").exists(), "installer ran despite uv present"
    assert res.stdout == "", f"stdout not clean: {res.stdout!r}"


def test_uv_selfheal_installs_uv_when_missing(tmp_path):
    # uv absent -> the astral installer runs, lands uv in ~/.local/bin, the
    # re-check finds it, and the launcher proceeds. All bootstrap output stays
    # off stdout (the MCP channel).
    scribe = _make_scribe(tmp_path)
    stubbin = _stubbin(tmp_path, uv=False, curl=CURL_INSTALL_OK)
    uv_src = _write_exec(tmp_path / "uv-stub-src", UV_STUB)
    res = _run(scribe, tmp_path, stubbin, extra_env={"UV_STUB_SRC": str(uv_src)})
    assert res.returncode == 0, res.stderr
    assert (tmp_path / "curl-ran").exists(), "installer must run when uv is missing"
    assert (tmp_path / "home" / ".local" / "bin" / "uv").exists()
    assert res.stdout == "", f"stdout not clean: {res.stdout!r}"
    assert "uv not found" in res.stderr
    assert "INSTALLER_STDOUT_MARKER" in res.stderr


def test_uv_missing_and_offline_errors_without_hang(tmp_path):
    # uv absent + offline -> a clear stderr error and a non-zero exit, and no
    # hang (the _run timeout would otherwise trip).
    scribe = _make_scribe(tmp_path)
    stubbin = _stubbin(tmp_path, uv=False, curl=CURL_OFFLINE)
    res = _run(scribe, tmp_path, stubbin)
    assert res.returncode != 0, "must exit non-zero when uv can't be installed"
    assert (tmp_path / "curl-ran").exists(), "installer must be attempted"
    assert "uv install failed" in res.stderr
    assert "online" in res.stderr
    assert res.stdout == "", f"stdout not clean: {res.stdout!r}"
    # The "no hang" guarantee rests on curl's connect/total timeouts: a stub can't
    # exercise the real SYN-retry timeout (it replaces curl), but asserting the
    # launcher *passes* the flags locks the mechanism in — strip them from the
    # launcher and this fails. A bare DNS failure returns fast either way, so
    # without this the flags are invisible to the suite.
    argv = (tmp_path / "curl-argv").read_text().splitlines()
    assert "--connect-timeout" in argv, f"curl missing --connect-timeout: {argv}"
    assert "--max-time" in argv, f"curl missing --max-time: {argv}"


def test_dead_interpreter_symlink_triggers_rebuild(tmp_path):
    # A foreign venv: dead bin/python symlink, but a present -x entry point and
    # a hash marker that already matches — so *only* the dead-interpreter guard
    # can force the rebuild.
    scribe = _make_scribe(tmp_path)
    stubbin = _stubbin(tmp_path, uv=True, curl=CURL_OFFLINE)

    venv = scribe / ".venv-stable"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").symlink_to("/nonexistent-xyz/python3.11")
    _write_exec(venv / "bin" / "bujo-scribe-mcp", "#!/bin/sh\nexit 0\n")
    (venv / ".installed-wheel-hash").write_text(_wheel_hash(scribe))
    marker = venv / "OLD_VENV_MARKER"
    marker.write_text("carried over from another machine")

    res = _run(scribe, tmp_path, stubbin)
    assert res.returncode == 0, res.stderr
    assert res.stdout == "", f"stdout not clean: {res.stdout!r}"
    assert not marker.exists(), "stale venv must be wiped, not reused"
    resolved = os.path.realpath(venv / "bin" / "python")
    assert Path(resolved).exists(), (
        "rebuilt bin/python must resolve to a real interpreter"
    )
    # The rebuild must resync the hash marker to the current wheel. Without
    # this, a regression that stops rewriting it slips through: the wipe above
    # deletes the old marker, so the reinstall fires regardless — but then
    # every *future* launch reinstalls too (empty marker != wheel hash).
    assert (venv / ".installed-wheel-hash").read_text().strip() == _wheel_hash(
        scribe
    ), "rebuild must rewrite .installed-wheel-hash to the current wheel hash"


def test_dead_interpreter_guard_noop_when_venv_absent(tmp_path):
    # No venv yet -> the guard is skipped and the normal fresh build proceeds.
    scribe = _make_scribe(tmp_path)
    stubbin = _stubbin(tmp_path, uv=True, curl=CURL_OFFLINE)
    assert not (scribe / ".venv-stable").exists()
    res = _run(scribe, tmp_path, stubbin)
    assert res.returncode == 0, res.stderr
    assert res.stdout == "", f"stdout not clean: {res.stdout!r}"
    assert (scribe / ".venv-stable" / "bin" / "python").exists()


def test_dead_interpreter_guard_noop_when_interpreter_resolves(tmp_path):
    # Healthy venv (interpreter resolves, hash matches, entry point present) ->
    # no wipe and no rebuild, so a sentinel inside it survives untouched.
    #
    # This is also the portability pin: the stub PATH's readlink rejects `-f`
    # (old macOS), so a regression back to the non-portable `readlink -f`
    # guard would wipe this healthy venv and fail the KEEP assertion below.
    scribe = _make_scribe(tmp_path)
    stubbin = _stubbin(tmp_path, uv=True, curl=CURL_OFFLINE)

    venv = scribe / ".venv-stable"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").symlink_to(_real_python())
    _write_exec(venv / "bin" / "bujo-scribe-mcp", "#!/bin/sh\nexit 0\n")
    (venv / ".installed-wheel-hash").write_text(_wheel_hash(scribe))
    keep = venv / "KEEP_VENV_MARKER"
    keep.write_text("healthy venv, must be reused")

    res = _run(scribe, tmp_path, stubbin)
    assert res.returncode == 0, res.stderr
    assert res.stdout == "", f"stdout not clean: {res.stdout!r}"
    assert keep.exists(), "healthy venv must not be rebuilt"

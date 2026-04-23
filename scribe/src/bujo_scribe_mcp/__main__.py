"""Entry point for `bujo-scribe-mcp` CLI."""

from __future__ import annotations

import sys

from bujo_scribe_mcp import __version__


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in {"serve", "--serve"}:
        from bujo_scribe_mcp.server import run_stdio

        run_stdio()
        return

    if args[0] in {"-v", "--version", "version"}:
        # Print just the version string (no prefix) so shell tooling can
        # consume it directly. The launcher uses this to compare installed
        # vs bundled-wheel version and auto-update on mismatch.
        print(__version__)
        return

    if args[0] in {"-h", "--help", "help"}:
        print(
            "Usage: bujo-scribe-mcp [serve|version]\n"
            "\n"
            "  serve     Start the MCP server over stdio (default).\n"
            "  version   Print the installed version and exit.\n"
        )
        return

    print(f"bujo-scribe-mcp: unknown command '{args[0]}'", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()

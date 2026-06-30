"""``controls`` — turn a NSW site location into the planning controls.

Examples:
    controls --lot 5/DP12345 --dev-type dwelling-house
    controls --coords 151.1043,-33.8136
    controls "1 Devlin St, Ryde NSW" --dev-type dual-occupancy --json
"""
from __future__ import annotations

import argparse
import json
import sys

from . import dcp as dcp_mod
from . import lep, locate, sheet


def _parse_coords(s: str) -> tuple[float, float]:
    try:
        a, b = (p.strip() for p in s.split(","))
        return float(a), float(b)
    except Exception as exc:  # noqa: BLE001
        raise argparse.ArgumentTypeError(f"coords must be 'lon,lat' — got {s!r}") from exc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="controls", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("address", nargs="?", help="street address (geocoded, approximate)")
    src.add_argument("--lot", help="lot/plan reference, e.g. 5/DP12345")
    src.add_argument("--coords", type=_parse_coords, metavar="LON,LAT",
                     help="exact coordinates as lon,lat (WGS84)")
    p.add_argument("--dev-type", help="dwelling-house | dual-occupancy (enables the DCP section)")
    p.add_argument("--council", default="ryde", help="council DCP to use (default: ryde)")
    p.add_argument("--json", action="store_true", help="emit JSON instead of a text sheet")
    return p


def main(argv: list[str] | None = None) -> int:
    # The sheet uses ≥, ², ×, etc. Windows consoles default to cp1252 and choke.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001 — older/odd stdouts; nothing to do
        pass
    args = build_parser().parse_args(argv)
    try:
        site = locate.resolve(coords=args.coords, lot=args.lot, address=args.address)
    except (ValueError, LookupError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    env = lep.envelope(site)

    dcp_result = None
    if args.dev_type:
        try:
            dcp_result = dcp_mod.controls_for(args.dev_type, council=args.council)
        except dcp_mod.DcpNotFound as exc:
            print(f"warning: {exc}", file=sys.stderr)

    if args.json:
        print(json.dumps(sheet.render_json(site, env, dcp_result), indent=2, ensure_ascii=False))
    else:
        print(sheet.render_text(site, env, dcp_result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Download Ryde DCP PDFs past the Akamai WAF, into sources/.

The council's edge (Akamai/edgesuite) 403s a plain UA. The Referer + Sec-Fetch-*
headers below are what make it serve the file. Use this to refresh the source
PDFs you transcribe the curated YAML from — do NOT auto-parse numbers into the
YAML; a human reviews the transcription (no fabricated setbacks).

    python scripts/fetch_ryde_dcp.py
"""
from __future__ import annotations

import pathlib
import urllib.request

OUT = pathlib.Path(__file__).resolve().parents[1] / "sources"
BASE = "https://www.ryde.nsw.gov.au/files/assets/public/v/1/development/dcp/"
REFERER = ("https://www.ryde.nsw.gov.au/Planning-and-Development/"
           "Planning-Controls/Development-Control-Plan")

PARTS = {
    "part-3.3-dwelling-houses-dual-occupancy.pdf": "dcp-2014-3.3-dwelling-houses-and-dual-occupancy.pdf",
    "part-1.0-introduction.pdf": "dcp-2014-1.0-introduction.pdf",
    "part-9.3-parking.pdf": "dcp-2014-9.3-parking-controls.pdf",  # filename may vary; adjust if 404
}

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer": REFERER,
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}


def fetch(remote: str) -> bytes:
    req = urllib.request.Request(BASE + remote, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for local, remote in PARTS.items():
        try:
            data = fetch(remote)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {remote}: {exc}")
            continue
        if not data.startswith(b"%PDF"):
            print(f"FAIL {remote}: not a PDF (WAF block?) — {data[:40]!r}")
            continue
        (OUT / local).write_bytes(data)
        print(f"OK   {local}  ({len(data):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

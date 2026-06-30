"""Council DCP controls from a curated, checked-in YAML (Ryde 2014 for now).

Why curated data and not live RAG over the PDFs: a single council's DCP is a
small, stable set of tables. A checked-in YAML is deterministic, testable,
citable clause-by-clause, and reviewable by a human — none of which a runtime
LLM call gives you. RAG earns its place only when generalising across many
councils' PDFs; that is a later phase, not Ryde-only v1.
"""
from __future__ import annotations

import importlib.resources as resources
from dataclasses import dataclass

import yaml

_DATA_PKG = "nsw_site_controls.data"

# Accept a range of spellings -> canonical dev_type key.
_ALIASES = {
    "dwelling": "dwelling-house",
    "dwelling house": "dwelling-house",
    "dwelling_house": "dwelling-house",
    "dwelling-house": "dwelling-house",
    "house": "dwelling-house",
    "dual": "dual-occupancy",
    "dual occ": "dual-occupancy",
    "dual occupancy": "dual-occupancy",
    "dual_occupancy": "dual-occupancy",
    "dual-occupancy": "dual-occupancy",
    "duplex": "dual-occupancy",
}


@dataclass
class DcpControl:
    control: str
    value: str
    clause: str


@dataclass
class DcpResult:
    council: str
    instrument: str
    source_part: str
    dev_type: str
    dev_label: str
    controls: list[DcpControl]
    note: str = ""
    source_url: str = ""
    retrieved: str = ""


class DcpNotFound(LookupError):
    pass


def load(council: str = "ryde") -> dict:
    fname = f"{council.lower()}_dcp_2014.yaml"
    try:
        text = resources.files(_DATA_PKG).joinpath(fname).read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise DcpNotFound(f"no curated DCP for council {council!r} ({fname})") from exc
    return yaml.safe_load(text)


def normalise_dev_type(dev_type: str) -> str | None:
    return _ALIASES.get((dev_type or "").strip().lower())


def available_dev_types(data: dict) -> list[str]:
    return list(data.get("dev_types", {}).keys())


def controls_for(dev_type: str, *, council: str = "ryde", data: dict | None = None) -> DcpResult:
    data = data or load(council)
    canonical = normalise_dev_type(dev_type)
    devs = data.get("dev_types", {})
    if canonical is None or canonical not in devs:
        raise DcpNotFound(
            f"dev-type {dev_type!r} not in {data.get('council', council)} DCP. "
            f"Available: {', '.join(available_dev_types(data))}"
        )
    block = devs[canonical]
    controls = [DcpControl(c["control"], c["value"], c.get("clause", "")) for c in block.get("controls", [])]
    return DcpResult(
        council=data.get("council", council),
        instrument=data.get("instrument", ""),
        source_part=data.get("source_part", ""),
        dev_type=canonical,
        dev_label=block.get("label", canonical),
        controls=controls,
        note=data.get("note", ""),
        source_url=data.get("source_url", ""),
        retrieved=data.get("retrieved", ""),
    )

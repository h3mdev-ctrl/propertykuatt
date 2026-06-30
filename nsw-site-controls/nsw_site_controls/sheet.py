"""Render the Site Control Sheet — text for humans, dict for ``--json``.

Every control line names its source (the LEP/EPI for envelope controls, the
clause for DCP controls). No fabricated precision: the DCP setback line repeats
the council's wording and points at the clause, it does not invent a number.
"""
from __future__ import annotations

from .dcp import DcpResult
from .lep import Envelope
from .locate import Site

DISCLAIMER = (
    "Decision-support only. Generated from public NSW spatial data and a curated "
    "transcription of the council DCP. It is NOT planning advice or a certificate. "
    "Verify against the source instruments / a planner / a s10.7 certificate before "
    "lodging a DA."
)

REFORM_WARNING = (
    "This is a residential zone — the NSW Low & Mid-Rise Housing reforms (2024–2025) "
    "may permit additional dwelling types, height and FSR here that the base LEP layer "
    "does NOT show. Check the Housing SEPP / reform mapping before assuming these limits."
)


def _is_residential(env: Envelope) -> bool:
    z = env.results.get("zoning")
    if not z or not z.present:
        return False
    for v in z.values:
        code = str(v.value or "").upper()
        lab = str(v.label or "").lower()
        if code.startswith("R") or "residential" in lab:
            return True
    return False


def _fmt_value(cv) -> str:
    parts = [str(cv.value)]
    if cv.unit:
        parts.append(str(cv.unit))
    s = " ".join(parts)
    if cv.label and str(cv.label) != str(cv.value):
        s += f"  ({cv.label})"
    return s


def render_text(site: Site, env: Envelope, dcp: DcpResult | None = None) -> str:
    L: list[str] = []
    L.append("=" * 64)
    L.append("NSW SITE CONTROL SHEET")
    L.append("=" * 64)
    L.append(f"Location : {site.lon:.6f}, {site.lat:.6f}  [{site.source}]")
    if site.lotidstring:
        L.append(f"Lot/DP   : {site.lotidstring}")
    if site.area_m2:
        src = {"planlotarea": "cadastre planlotarea",
               "geometry": "from parcel geometry"}.get(site.area_source, "cadastre")
        L.append(f"Site area: {site.area_m2:.0f} m²  ({src})")
    L.append("")

    L.append("-- LEP / SEPP envelope -------------------------------------------")
    for key, res in env.results.items():
        name = res.spec.name
        if res.error:
            L.append(f"  {name:<22}: (unavailable — {res.error.splitlines()[0][:60]})")
            continue
        if not res.present:
            L.append(f"  {name:<22}: none mapped")
            continue
        if res.spec.kind == "heritage":
            for cv in res.values:
                L.append(f"  {name:<22}: {cv.value}  [{cv.label}]  ({cv.epi})")
            continue
        for i, cv in enumerate(res.values):
            tag = name if i == 0 else ""
            line = f"  {tag:<22}: {_fmt_value(cv)}"
            if cv.epi:
                line += f"  — {cv.epi}"
            L.append(line)
        if res.is_split:
            L.append(f"  {'':<22}  ^ site straddles {len(res.values)} {name.lower()} areas")

    if env.max_gfa_m2:
        gfa = " or ".join(f"{g:,} m²" for g in env.max_gfa_m2)
        L.append(f"  {'Max GFA (derived)':<22}: ≈ {gfa}   (FSR × site area)")
    if env.subdivision:
        L.append(f"  {'Subdivision':<22}: {env.subdivision}")
    for n in env.notes:
        L.append(f"  • {n}")
    L.append("")

    if dcp is not None:
        L.append(f"-- {dcp.council} DCP — {dcp.dev_label} --------------------")
        L.append(f"   ({dcp.instrument}, {dcp.source_part}; retrieved {dcp.retrieved})")
        for c in dcp.controls:
            L.append(f"  • {c.control}: {c.value}")
            L.append(f"      └ clause {c.clause}")
        L.append("")

    warnings = list(site.warnings)
    if _is_residential(env):
        warnings.append(REFORM_WARNING)
    if warnings:
        L.append("-- Warnings ------------------------------------------------------")
        for w in warnings:
            L.append(f"  ! {w}")
        L.append("")

    L.append("-" * 64)
    L.append(DISCLAIMER)
    return "\n".join(L)


def render_json(site: Site, env: Envelope, dcp: DcpResult | None = None) -> dict:
    out = {
        "site": {
            "lon": site.lon, "lat": site.lat, "source": site.source,
            "lotidstring": site.lotidstring, "area_m2": site.area_m2,
            "area_source": site.area_source, "warnings": list(site.warnings),
        },
        "envelope": {},
        "derived": {"max_gfa_m2": env.max_gfa_m2, "subdivision": env.subdivision,
                    "notes": env.notes},
        "disclaimer": DISCLAIMER,
    }
    for key, res in env.results.items():
        out["envelope"][key] = {
            "name": res.spec.name,
            "error": res.error,
            "values": [
                {"value": cv.value, "label": cv.label, "epi": cv.epi, "unit": cv.unit}
                for cv in res.values
            ],
        }
    if _is_residential(env):
        out["site"]["warnings"].append(REFORM_WARNING)
    if dcp is not None:
        out["dcp"] = {
            "council": dcp.council, "instrument": dcp.instrument,
            "source_part": dcp.source_part, "dev_type": dcp.dev_type,
            "dev_label": dcp.dev_label, "retrieved": dcp.retrieved,
            "controls": [
                {"control": c.control, "value": c.value, "clause": c.clause}
                for c in dcp.controls
            ],
        }
    return out

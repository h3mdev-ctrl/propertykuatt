"""Query the LEP/SEPP spatial layers for a site and build the build-envelope.

    Site --(polygon if known, else point)--> for each LayerSpec in registry:
        query layer -> features -> [ControlValue, ...]   (multiple = split site)
    derive: max GFA = FSR x area ; subdivision feasibility vs min lot size

A layer that errors does NOT sink the whole envelope — its ControlResult carries
the error and the sheet renders the rest (same partial-render discipline as the
butler brief scripts).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import arcgis
from .locate import Site
from .registry import LAYER_REGISTRY, PLANNING_SERVICE, LayerSpec


@dataclass
class ControlValue:
    value: object
    label: str | None = None
    epi: str | None = None
    unit: str | None = None


@dataclass
class ControlResult:
    spec: LayerSpec
    values: list[ControlValue] = field(default_factory=list)
    error: str | None = None

    @property
    def present(self) -> bool:
        return bool(self.values)

    @property
    def is_split(self) -> bool:
        return len(self.values) > 1


@dataclass
class Envelope:
    results: dict[str, ControlResult]
    max_gfa_m2: list[float] = field(default_factory=list)   # one per distinct FSR
    subdivision: str | None = None
    notes: list[str] = field(default_factory=list)


def _distinct(values: list[ControlValue]) -> list[ControlValue]:
    seen, out = set(), []
    for v in values:
        key = (str(v.value), v.epi)
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out


def parse_features(spec: LayerSpec, feats: list[dict]) -> ControlResult:
    values: list[ControlValue] = []
    for feat in feats:
        attrs = feat.get("attributes", {})
        raw = attrs.get(spec.value_field)
        if raw in (None, "", " "):
            continue
        values.append(ControlValue(
            value=raw,
            label=attrs.get(spec.label_field) if spec.label_field else None,
            epi=attrs.get(spec.epi_field),
            unit=attrs.get(spec.unit_field) if spec.unit_field else None,
        ))
    return ControlResult(spec=spec, values=_distinct(values))


def envelope(site: Site, *, service: str = PLANNING_SERVICE,
             registry=LAYER_REGISTRY, query_fn=arcgis.query) -> Envelope:
    if site.parcel:
        geom, gtype = site.parcel, "esriGeometryPolygon"
    else:
        geom, gtype = arcgis.point_geometry(site.lon, site.lat), "esriGeometryPoint"

    results: dict[str, ControlResult] = {}
    for spec in registry:
        try:
            feats = query_fn(service, spec.layer_id, geometry=geom, geometry_type=gtype)
            results[spec.key] = parse_features(spec, feats)
        except arcgis.ArcGISError as exc:
            results[spec.key] = ControlResult(spec=spec, error=str(exc))

    env = Envelope(results=results)
    _derive(site, env)
    return env


def _derive(site: Site, env: Envelope) -> None:
    fsr = env.results.get("fsr")
    if fsr and fsr.present and site.area_m2:
        for cv in fsr.values:
            try:
                env.max_gfa_m2.append(round(float(cv.value) * site.area_m2))
            except (TypeError, ValueError):
                pass
    elif fsr and fsr.present and not site.area_m2:
        env.notes.append("max GFA not computed — site area unknown (give a lot/DP or coords on a parcel)")

    min_lot = env.results.get("min_lot")
    if min_lot and min_lot.present and site.area_m2:
        try:
            sizes = [float(v.value) for v in min_lot.values]
            smallest = min(sizes)
            if smallest > 0:
                n = int(site.area_m2 // smallest)
                env.subdivision = (
                    f"{site.area_m2:.0f} m² / {smallest:.0f} m² min lot "
                    f"= up to {n} lot(s) on min-lot-size alone" if n >= 1
                    else f"site ({site.area_m2:.0f} m²) is below the {smallest:.0f} m² minimum lot size"
                )
        except (TypeError, ValueError):
            pass

"""Where every control lives. Adding a control = adding a row here, not code.

Verified 2026-06-29 against the live service metadata:
``Planning/EPI_Primary_Planning_Layers`` is the flat service (one layer id per
control), which is far simpler to query than the nested Principal_Planning
group service. Layer ids and value-field names below come from each layer's
``?f=json`` field definition.
"""
from __future__ import annotations

from dataclasses import dataclass

# --- services ---------------------------------------------------------------
PLANNING_SERVICE = (
    "https://mapprod1.environment.nsw.gov.au/arcgis/rest/services/"
    "Planning/EPI_Primary_Planning_Layers/MapServer"
)
CADASTRE_SERVICE = (
    "https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Cadastre/MapServer"
)
CADASTRE_LOT_LAYER = 9


@dataclass(frozen=True)
class LayerSpec:
    """One LEP/SEPP control layer and how to read its headline value."""

    key: str            # machine key, e.g. "zoning"
    name: str           # human label for the sheet
    layer_id: int
    value_field: str    # attribute holding the control value
    label_field: str | None = None   # attribute holding a human label
    epi_field: str = "EPI_NAME"       # the controlling instrument's name
    unit_field: str | None = None     # attribute holding units, if any
    kind: str = "scalar"             # "scalar" | "heritage"


# Order = display order on the sheet.
LAYER_REGISTRY: list[LayerSpec] = [
    LayerSpec("zoning", "Land zoning", 2, value_field="SYM_CODE", label_field="LAY_CLASS"),
    LayerSpec("fsr", "Floor space ratio (FSR)", 1, value_field="FSR", label_field="SYM_CODE"),
    LayerSpec("height", "Max building height", 5, value_field="MAX_B_H",
              label_field="SYM_CODE", unit_field="UNITS"),
    LayerSpec("min_lot", "Minimum lot size", 4, value_field="LOT_SIZE",
              label_field="SYM_CODE", unit_field="UNITS"),
    LayerSpec("heritage", "Heritage", 0, value_field="H_NAME",
              label_field="SIG", kind="heritage"),
]

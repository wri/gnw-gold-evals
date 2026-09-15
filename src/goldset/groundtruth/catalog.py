"""Provides all info for the request builder, given a dataset_id

Given a dataset_id, this provides:
- the URL to POST to
- payload shape
- time window (when start/end isn't specified)
- how to distinguish between datasets that use the same URL (TCL/TCLF for example)

This temporarily hardcodes info from from the snapshot at ``cases/zeno_catalog.json``
and ``src/agent/datasets/catalog/*.yml`` in project-zeno. 
"""

from __future__ import annotations

from dataclasses import dataclass

# How a dataset's payload is shaped beyond the mandatory ``aoi`` block.
#   none        AOI only
#   date        start_date/end_date + intersections
#   year        start_year/end_year
#   loss        start_year/end_year + forest_filter + intersections + canopy_cover
#   gain        start_year/end_year snapped to 5-year buckets + forest_filter
#   canopy      canopy_cover only
#   extent      forest_filter + canopy_cover
#   unsupported recognised, but not buildable here yet
PayloadStyle = str

DEFAULT_CANOPY_COVER = 30


@dataclass(frozen=True)
class Dataset:
    """One dataset's analytics contract."""

    dataset_id: str
    name: str
    endpoint: str
    style: PayloadStyle
    start_date: str
    end_date: str | None = None
    # content_date_fixed: the window is pinned and never extends, so a
    # hand-verified answer on this dataset is genuinely stable.
    fixed: bool = False
    # Datasets 4, 8 and 10 share one endpoint and are separated only by this.
    intersections: tuple[str, ...] = ()


# end_date None means "to today" — zeno's revise_date_range substitutes it.
DATASETS: dict[str, Dataset] = {
    "0": Dataset("0", "Global all ecosystem disturbance alerts (DIST-ALERT)",
                 "/v0/land_change/dist_alerts/analytics", "date", "2023-12-01"),
    "1": Dataset("1", "Global land cover",
                 "/v0/land_change/land_cover_change/analytics", "none",
                 "2015-01-01", "2024-12-31"),
    "2": Dataset("2", "Global natural/semi-natural grassland extent",
                 "/v0/land_change/grasslands/analytics", "year",
                 "2000-01-01", "2022-12-31"),
    "3": Dataset("3", "SBTN Natural Lands Map",
                 "/v0/land_change/natural_lands/analytics", "none",
                 "2020-01-01", "2020-12-31", fixed=True),
    "4": Dataset("4", "Tree cover loss",
                 "/v0/land_change/tree_cover_loss/analytics", "loss",
                 "2001-01-01", "2025-12-31"),
    "5": Dataset("5", "Tree cover gain",
                 "/v0/land_change/tree_cover_gain/analytics", "gain",
                 "2000-01-01", "2020-12-31"),
    "6": Dataset("6", "Forest greenhouse gas net flux",
                 "/v0/land_change/carbon_flux/analytics", "canopy",
                 "2001-01-01", "2025-12-31"),
    "7": Dataset("7", "Tree cover",
                 "/v0/land_change/tree_cover/analytics", "extent",
                 "2000-01-01", "2000-12-31", fixed=True),
    "8": Dataset("8", "Tree cover loss by dominant driver",
                 "/v0/land_change/tree_cover_loss/analytics", "loss",
                 "2001-01-01", "2025-12-31", fixed=True,
                 intersections=("driver",)),
    "9": Dataset("9", "Deforestation (sLUC) Emission Factors by Agricultural Crop",
                 "/v0/land_change/deforestation_luc_emissions_factor/analytics",
                 "unsupported", "2020-01-01", "2024-12-31", fixed=True),
    "10": Dataset("10", "Tree cover loss due to fires",
                  "/v0/land_change/tree_cover_loss/analytics", "loss",
                  "2001-01-01", "2025-12-31", intersections=("fire",)),
    "11": Dataset("11", "Integrated alerts",
                  "/v0/land_change/integrated_alerts/analytics", "date",
                  "2023-12-01"),
    "12": Dataset("12", "Land GHG Monitoring System (LGMS)",
                  "/v0/land_change/land_ghg_inventory/analytics", "none",
                  "2016-01-01"),
}

# expected.aoi_source -> the analytics API's aoi.type. Lowercased on lookup
# because the case set spells it both "Landmark" (5 cases) and "landmark" (2).
AOI_TYPES: dict[str, str] = {
    "gadm": "admin",
    "kba": "key_biodiversity_area",
    "wdpa": "protected_area",
    "landmark": "indigenous_land",
}


def dataset_for(dataset_id: str) -> Dataset | None:
    return DATASETS.get(str(dataset_id).strip())

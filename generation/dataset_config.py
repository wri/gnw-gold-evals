"""Per-dataset generation config, shared by generate_cases, validate_manifest
and promote_cases.

Ported from gnw-evals ``eval-metrics-slice-1`` (the Phase 2 numeric-expansion
work) into the CHALLENGE harness. The manifest is dataset-agnostic (a superset
of parameter columns); this table is what makes a manifest row resolve to the
right expected values and the right validation surface for its dataset. Facts
mirror the catalog YAMLs in ``project-zeno/src/agent/datasets/catalog/`` —
snapshot ``cases/zeno_catalog.json`` — and the analytics handler
(``src/agent/datasets/handlers/analytics_handler.py``).

Changes from the gnw-evals original:

- DIST-ALERT (id 0) is gone: ``dist_alert.yml`` no longer exists on
  project-zeno main (zeno@31a4d1e) — its cells were retired with it. Alert
  coverage lives on ``integrated_alerts`` (id 11).
- LGMS (id 12) is deliberately absent: it is excluded from the default agent
  profile, and the CHALLENGE canonical series runs prod + default.
- ``cohort`` names the CHALLENGE cohort (``case.group``) the dataset's cases
  land in; the CHALLENGE set is the intent (set → cohort → case).

Only the numeric-intent surface (quantification/trend/comparison) is modelled
here. Each config declares:

- ``dataset_id`` / ``slug`` - catalog identity (slug = catalog filename stem).
- ``cohort`` - short CHALLENGE cohort name for this dataset.
- ``intents`` - which numeric intents apply (trend omitted for snapshot or
  aggregate datasets whose product forbids a time series).
- ``date_mode`` - how a manifest row's dates become expected dates:
  ``years`` (``start_year``/``end_year`` → ``YYYY-01-01``/``YYYY-12-31``),
  ``dates`` (``start_date``/``end_date`` verbatim, for alert streams), or
  ``blank`` (dataset ignores/fixes dates → no date expectation is scored).
- ``canopy_default`` - ``"30"`` for TCL-family + flux datasets that take a
  canopy threshold, else ``None``. Only an explicit non-default canopy in the
  manifest becomes a scored ``dataset_parameters`` expectation; the default is
  recorded in notes, unscored (the agent may or may not surface it in state).
- ``fixed_intersections`` - intersection value intrinsic to choosing this
  dataset (``driver`` for id 8, ``fire`` for id 10); informational only in
  the CHALLENGE port (no state surface scores it).
- ``forest_layers`` - legal ``forest_filter`` values; these are the dataset's
  catalog context layers, scored via ``context_layer`` (blank forest_filter →
  ``no_selection``: the wording explicitly opts out of forest-type filters).
- ``params`` - extra manifest columns this dataset can carry
  (``crop_types``, ``gas_types``, ``land_cover_classes``, ``intersections``);
  carried into case notes, unscored until an evaluator exists.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DatasetConfig:
    """Generation + validation surface for one catalog dataset."""

    dataset_id: str
    slug: str
    cohort: str
    intents: frozenset[str]
    date_mode: str  # "years" | "dates" | "blank"
    canopy_default: str | None = None
    fixed_intersections: str = ""
    forest_layers: frozenset[str] = field(default_factory=frozenset)
    params: frozenset[str] = field(default_factory=frozenset)
    aoi_subtype: str = "country"
    aoi_source: str = "gadm"


_ALL_THREE = frozenset({"quantification", "trend", "comparison"})
_QUANT_COMP = frozenset({"quantification", "comparison"})

DATASET_CONFIGS: dict[str, DatasetConfig] = {
    "global_land_cover": DatasetConfig(
        dataset_id="1",
        slug="global_land_cover",
        cohort="land-cover",
        intents=_QUANT_COMP,
        date_mode="blank",
        params=frozenset({"land_cover_classes"}),
    ),
    "global_natural_semi_natural_grassland_extent": DatasetConfig(
        dataset_id="2",
        slug="global_natural_semi_natural_grassland_extent",
        cohort="grasslands",
        intents=_ALL_THREE,
        date_mode="years",
    ),
    "sbtn_natural_lands_map": DatasetConfig(
        dataset_id="3",
        slug="sbtn_natural_lands_map",
        cohort="natural-lands",
        intents=_QUANT_COMP,
        date_mode="blank",
    ),
    "tree_cover_loss": DatasetConfig(
        dataset_id="4",
        slug="tree_cover_loss",
        cohort="tcl",
        intents=_ALL_THREE,
        date_mode="years",
        canopy_default="30",
        forest_layers=frozenset({"primary_forest", "intact_forest"}),
        params=frozenset({"intersections"}),
    ),
    "tree_cover_gain": DatasetConfig(
        dataset_id="5",
        slug="tree_cover_gain",
        cohort="tc-gain",
        intents=_QUANT_COMP,
        date_mode="years",
    ),
    "forest_greenhouse_gas_net_flux": DatasetConfig(
        dataset_id="6",
        slug="forest_greenhouse_gas_net_flux",
        cohort="ghg-flux",
        intents=_QUANT_COMP,
        date_mode="blank",
        canopy_default="30",
        params=frozenset({"gas_types"}),
    ),
    "tree_cover": DatasetConfig(
        dataset_id="7",
        slug="tree_cover",
        cohort="tree-cover",
        intents=_QUANT_COMP,
        date_mode="blank",
        canopy_default="30",
        forest_layers=frozenset({"primary_forest"}),
    ),
    "tree_cover_loss_by_dominant_driver": DatasetConfig(
        dataset_id="8",
        slug="tree_cover_loss_by_dominant_driver",
        cohort="tcl-drivers",
        intents=_QUANT_COMP,
        date_mode="blank",
        canopy_default="30",
        fixed_intersections="driver",
        params=frozenset({"intersections"}),
    ),
    "deforestation_sluc_emission_factors_by_agricultural_crop": DatasetConfig(
        dataset_id="9",
        slug="deforestation_sluc_emission_factors_by_agricultural_crop",
        cohort="sluc",
        intents=_ALL_THREE,
        date_mode="years",
        params=frozenset({"crop_types", "gas_types"}),
    ),
    "tree_cover_loss_from_fires": DatasetConfig(
        dataset_id="10",
        slug="tree_cover_loss_from_fires",
        cohort="tcl-fires",
        intents=_ALL_THREE,
        date_mode="years",
        canopy_default="30",
        fixed_intersections="fire",
        forest_layers=frozenset({"primary_forest", "intact_forest"}),
        params=frozenset({"intersections"}),
    ),
    "integrated_alerts": DatasetConfig(
        dataset_id="11",
        slug="integrated_alerts",
        cohort="integrated-alerts",
        intents=_ALL_THREE,
        date_mode="dates",
    ),
}

SLUG_BY_ID = {cfg.dataset_id: slug for slug, cfg in DATASET_CONFIGS.items()}

# Set slug (= intent) → case-id prefix.
INTENT_ID_PREFIX = {
    "quantification": "ch-quant",
    "trend": "ch-trend",
    "comparison": "ch-comp",
}


def config_for_manifest(filename: str) -> DatasetConfig:
    """Resolve the dataset config from a ``<slug>__<intent>.manifest.csv`` name.

    The slug can itself contain ``__`` only if a catalog ever does; we match
    the longest known slug that prefixes the filename to stay unambiguous.
    """
    stem = filename.removesuffix(".manifest.csv").removesuffix(".csv")
    for slug in sorted(DATASET_CONFIGS, key=len, reverse=True):
        if stem == slug or stem.startswith(f"{slug}__"):
            return DATASET_CONFIGS[slug]
    raise KeyError(f"no dataset config matches manifest {filename!r}")

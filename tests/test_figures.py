"""Figure checks (draft-5): formulas over the agent's own pulled table."""

from types import SimpleNamespace

import pytest

from goldset.evaluators import figures
from goldset.evaluators.figures import (
    Aggregate,
    Combined,
    FigureError,
    candidates,
    claim_sentence,
    compute,
    evaluate_answer_period,
    evaluate_figure_claim,
    evaluate_figures,
    parse_claim,
    parse_figures,
    parse_formula,
    stated_numbers,
    validate,
)

TCL = [
    {"aoi_id": "PER.12", "tree_cover_loss_year": year, "area_ha": area}
    for year, area in [(2018, 100.0), (2019, 200.0), (2020, 300.0), (2021, 400.0)]
] + [{"aoi_id": "PER.23", "tree_cover_loss_year": 2020, "area_ha": 50.0}]


def _state(answer, *tables):
    urls = [f"https://analytics/{i}" for i in range(len(tables))]
    return (
        {"messages": [SimpleNamespace(content=answer)],
         "statistics": [{"source_url": u, "data": {}} for u in urls]},
        dict(zip(urls, tables, strict=True)),
    )


@pytest.fixture
def pulled(monkeypatch):
    """Serve tables by URL instead of fetching them."""
    def use(tables_by_url):
        def fake(url):
            rows = tables_by_url.get(url)
            if rows is None:
                return None
            columns = tuple(sorted({k for r in rows for k in r}))
            return columns, tuple(tuple(r.get(c) for c in columns) for r in rows)
        monkeypatch.setattr(figures, "_fetch", fake)
    return use


# ------------------------------------------------------------------ grammar


def test_parses_aggregates_conditions_and_groups():
    formula = parse_formula(
        "mean(area_ha) by tree_cover_loss_year where tree_cover_loss_year in 2018..2020"
        " and aoi_id = 'PER.12'"
    )
    assert formula == Aggregate(
        "mean", ("area_ha",), "tree_cover_loss_year",
        (figures.Condition("tree_cover_loss_year", "range", (2018, 2020)),
         figures.Condition("aoi_id", "=", ("PER.12",))),
    )
    assert isinstance(parse_formula("ratio(sum(a) where x = 1, sum(a))"), Combined)


def test_figures_split_into_alternatives_and_refs():
    parsed = parse_figures("sum(area_ha) | mean(area_ha) ; ref: max(area_ha) by year")
    assert [len(f.alternatives) for f in parsed] == [2, 1]
    assert [f.ref for f in parsed] == [False, True]


@pytest.mark.parametrize("bad", [
    "total(area_ha)", "sum(area ha)", "sum(area_ha) when year = 1", "ratio(sum(a))",
    "sum(area_ha) where year ~ 3",
])
def test_bad_formulas_fail_loudly(bad):
    with pytest.raises(FigureError):
        parse_figures(bad)


def test_validate_reports_case_errors():
    assert validate({"figure": "sum(area_ha)"}) == []
    assert validate({"figure": "sum(area_ha)", "figure_claim": "#1 > 0 :: a || b"}) == []
    assert validate({"figure": "sum(area_ha)", "figure_claim": "#2 > 0 :: a || b"})
    assert validate({"figure_claim": "#1 > 0 :: a || b"})


# -------------------------------------------------------------- computation


def test_sum_mean_and_grouped_aggregates():
    assert compute(parse_formula("sum(area_ha) where tree_cover_loss_year in 2018..2019"),
                   TCL) == 300.0
    # Annual mean across both areas' rows for 2020 is summed per year first.
    assert compute(parse_formula(
        "mean(area_ha) by tree_cover_loss_year where tree_cover_loss_year in 2019..2020"),
        TCL) == (200.0 + 350.0) / 2
    assert compute(parse_formula("max(area_ha) by tree_cover_loss_year"), TCL) == 400.0
    assert compute(parse_formula("count(area_ha) where aoi_id = 'per.23'"), TCL) == 1.0


def test_combined_figures():
    assert compute(parse_formula(
        "change(sum(area_ha) where tree_cover_loss_year = 2018, "
        "sum(area_ha) where tree_cover_loss_year = 2021)"), TCL) == 300.0
    assert compute(parse_formula(
        "ratio(sum(area_ha) where aoi_id = 'PER.23', sum(area_ha))"), TCL) == 50 / 1050


def test_a_missing_column_is_not_computable_and_tables_are_not_mixed():
    other = [{"land_cover_class": "Cropland", "area_ha": 9.0}]
    # sum(area_ha) per table, plus the union; never a figure from the wrong
    # dataset alone when the formula names a column only TCL has.
    by_year = parse_formula("sum(area_ha) where tree_cover_loss_year = 2021")
    assert candidates(by_year, [TCL, other]) == [400.0]
    unfiltered = parse_formula("sum(area_ha)")
    assert candidates(unfiltered, [TCL, other]) == [1050.0, 9.0, 1059.0]


# ---------------------------------------------------------------- the reply


def test_reads_numbers_with_scales_and_skips_years():
    stated = {s.text: s for s in stated_numbers(
        "In 2024 Bolivia lost 1.8 million hectares (1,813,615 ha), 4.3% of its forest,"
        " about 42 Mt CO2e, or 18,136 km²."
    )}
    assert stated["1.8 million"].value == pytest.approx(1.8e6)
    assert stated["1,813,615 ha"].value == 1813615
    assert stated["4.3%"].percent
    assert "2024" not in stated
    assert stated["42 Mt"].value == pytest.approx(42e6)
    assert stated["18,136 km²"].value == pytest.approx(1813600)


def _local(answer, language):
    return {s.text: s for s in stated_numbers(answer, language)}


def test_an_unknown_language_fails_loudly():
    with pytest.raises(ValueError, match="language"):
        stated_numbers("12 ha", "de")


def test_english_cases_keep_the_english_reading():
    # The frozen English BENCHMARK must score as before: "1.209" is 1.209.
    (stated,) = stated_numbers("about 1.209 Mha")
    assert stated.value == pytest.approx(1.209e6)
    assert stated.other is None


def test_reads_indonesian_replies_from_the_traces():
    # Replies Horizon gave Indonesian users (traces, 2026).
    stated = _local(
        "Indonesia kehilangan total **33.124.943,21 ha** (sekitar 10,46%)."
        " Emisi mencapai **53,17 juta MgCO2e**, fluks neto **+1,72 Miliar MgCO2e**."
        " Pada tahun **2016** luasnya **321.221 hektar**; fluks bersih negatif"
        " sebesar -7.856,30 tCO2e pada periode 2001-2025.",
        "id",
    )
    assert stated["33.124.943,21 ha"].value == pytest.approx(33124943.21)
    assert stated["33.124.943,21 ha"].precision == pytest.approx(0.005)
    assert stated["10,46%"].value == pytest.approx(10.46)
    assert stated["10,46%"].percent
    assert stated["53,17 juta"].value == pytest.approx(53.17e6)
    assert stated["1,72 Miliar"].value == pytest.approx(1.72e9)
    # The reply's own numbers show the comma is its decimal mark, so that is
    # the first reading; the other is kept.
    assert stated["321.221 hektar"].value == 321221
    assert stated["321.221 hektar"].other.value == pytest.approx(321.221)
    assert stated["-7.856,30 tCO2e"].value == pytest.approx(-7856.30)
    assert not {"2016", "2001", "2025"} & set(stated)


def test_reads_spanish_replies_in_either_convention():
    # Horizon's Spanish replies use both conventions (traces, 2026).
    english_form = _local(
        "Se registraron **434,487.33 ha**; el motor principal afectó"
        " **1.33 millones de hectáreas** y cerca de **19,582 hectáreas** en Oaxaca.",
        "es",
    )
    assert english_form["434,487.33 ha"].value == pytest.approx(434487.33)
    assert english_form["1.33 millones"].value == pytest.approx(1.33e6)
    assert english_form["19,582 hectáreas"].value == 19582
    # Here the English mark leads, and the local reading is kept.
    assert english_form["19,582 hectáreas"].other.value == pytest.approx(19.582)
    local_form = _local(
        "Cuerpos de agua: 1,10% (0,32 Mha). Pérdida: 393.170 hectáreas.", "es"
    )
    assert local_form["1,10%"].value == pytest.approx(1.10)
    assert local_form["0,32 Mha"].value == pytest.approx(0.32e6)
    assert local_form["393.170 hectáreas"].value == 393170
    assert local_form["393.170 hectáreas"].other.value == pytest.approx(393.17)


def test_reads_portuguese_replies():
    # Modelled on Horizon's Portuguese replies (traces, 2026): comma decimals,
    # dot grouping.
    stated = _local(
        "Em 2024 foram detectados **138,03 hectares** de distúrbio; a perda"
        " total foi de **1.234,5 ha** (cerca de 2,3%). O Brasil perdeu"
        " **2,3 milhões de hectares** e emitiu **1,2 bilhão de toneladas**"
        " de CO2e. Em **2016** a área era de **321.221 hectares**.",
        "pt",
    )
    assert stated["138,03 hectares"].value == pytest.approx(138.03)
    assert stated["1.234,5 ha"].value == pytest.approx(1234.5)
    assert stated["1.234,5 ha"].other is None
    assert stated["2,3%"].value == pytest.approx(2.3) and stated["2,3%"].percent
    assert stated["2,3 milhões"].value == pytest.approx(2.3e6)
    assert stated["1,2 bilhão"].value == pytest.approx(1.2e9)
    # The reply's comma decimals make "321.221" 321,221 first.
    assert stated["321.221 hectares"].value == 321221
    assert stated["321.221 hectares"].other.value == pytest.approx(321.221)
    assert "2016" not in stated


def test_reads_french_replies():
    # Modelled on Horizon's French replies (traces, 2026): comma decimals,
    # thousands grouped by a space.
    stated = _local(
        "Au total, **12 480 hectares** ont été perdus (2,3 % de la couverture),"
        " dont 1 234,5 ha en 2021. Les émissions atteignent **1,2 milliard de"
        " tonnes** de CO2e, et **3,4 millions d'hectares** restent intacts.",
        "fr",
    )
    assert stated["12 480 hectares"].value == 12480
    assert stated["2,3%"].value == pytest.approx(2.3) and stated["2,3%"].percent
    assert stated["1 234,5 ha"].value == pytest.approx(1234.5)
    assert stated["1,2 milliard"].value == pytest.approx(1.2e9)
    assert stated["3,4 millions"].value == pytest.approx(3.4e6)


@pytest.mark.parametrize("space", ["\u00a0", "\u202f", "\u2009"])
def test_a_fixed_space_groups_french_thousands(space):
    # French typesetting groups with a narrow no-break space; it only groups.
    (stated,) = stated_numbers(f"Au total, 1{space}234,5{space}ha.", "fr")
    assert stated.value == pytest.approx(1234.5)
    assert stated.other is None


@pytest.mark.parametrize(
    ("answer", "language", "text", "value"),
    [
        ("unas 3 mil hectáreas", "es", "3 mil", 3e3),
        ("2,5 mil millones de toneladas", "es", "2,5 mil millones", 2.5e9),
        ("1,2 billones de toneladas", "es", "1,2 billones", 1.2e12),
        ("un 12,5 por ciento", "es", "12,5por ciento", 12.5),
        ("sekitar 450 ribu hektar", "id", "450 ribu", 450e3),
        ("2,11 juta ha", "id", "2,11 juta", 2.11e6),
        ("3,4 triliun ton", "id", "3,4 triliun", 3.4e12),
        ("sebesar 4,9 persen", "id", "4,9persen", 4.9),
        ("18.136 km²", "id", "18.136 km²", 1813600),
        ("un 12,5 porciento", "es", "12,5porciento", 12.5),
        ("unos 25 kilómetros cuadrados", "es", "25 kilómetros cuadrados", 2500),
        ("seluas 25 kilometer persegi", "id", "25 kilometer persegi", 2500),
        ("1,2 millo\u0301n de hectáreas", "es", "1,2 millón", 1.2e6),
        ("cerca de 3 mil hectares", "pt", "3 mil", 3e3),
        ("1 milhão de hectares", "pt", "1 milhão", 1e6),
        ("2,3 milhões de hectares", "pt", "2,3 milhões", 2.3e6),
        ("4,5 bilhões de toneladas", "pt", "4,5 bilhões", 4.5e9),
        ("2,5 mil milhões de toneladas", "pt", "2,5 mil milhões", 2.5e9),
        ("1,2 trilhão de toneladas", "pt", "1,2 trilhão", 1.2e12),
        ("cerca de 12,5 por cento", "pt", "12,5por cento", 12.5),
        ("cerca de 25 quilômetros quadrados", "pt", "25 quilômetros quadrados", 2500),
        ("cerca de 25 quilómetros quadrados", "pt", "25 quilómetros quadrados", 2500),
        ("environ 3 mille hectares", "fr", "3 mille", 3e3),
        ("2,3 millions d'hectares", "fr", "2,3 millions", 2.3e6),
        ("1,2 milliard de tonnes", "fr", "1,2 milliard", 1.2e9),
        ("environ 12,5 pour cent", "fr", "12,5pour cent", 12.5),
        ("environ 25 kilomètres carrés", "fr", "25 kilomètres carrés", 2500),
    ],
)
def test_reads_local_scale_and_percent_words(answer, language, text, value):
    assert _local(answer, language)[text].value == pytest.approx(value)


def test_a_number_with_no_clear_reading_keeps_both():
    # Nothing in the reply settles the mark, so Horizon's habit in the case
    # language gives the first reading and the other is kept.
    (stated,) = stated_numbers("Se perdieron 19,582 hectáreas.", "es")
    assert stated.value == 19582
    assert stated.other.value == pytest.approx(19.582)
    (stated,) = stated_numbers("Total kehilangan 64.435 hektar.", "id")
    assert stated.value == 64435
    assert stated.other.value == pytest.approx(64.435)
    # A reply that mixes both conventions settles nothing either.
    mixed = _local("1,5 Mha y 2.5 Mha, con 1.209 ha", "es")
    assert mixed["1.209 ha"].other is not None


def test_a_clear_number_does_not_settle_an_ambiguous_one():
    # The reply's mark only orders the readings; the other is always kept.
    (stated,) = [s for s in stated_numbers("Pico de 16,08 millones y 8,374 ha", "es")
                 if s.text.startswith("8,374")]
    assert stated.value == pytest.approx(8.374)
    assert stated.other.value == 8374


def test_a_clear_shape_has_one_reading():
    assert _local("unas 0,125 ha", "es")["0,125 ha"].value == pytest.approx(0.125)
    assert _local("unas 0,125 ha", "es")["0,125 ha"].other is None
    assert _local("seluas 0.123 ha", "id")["0.123 ha"].value == pytest.approx(0.123)
    assert _local("seluas 0.123 ha", "id")["0.123 ha"].other is None
    # More than three whole digits cannot be grouped, so the mark is decimal.
    stated = _local("unas 1234,567 ha", "es")["1234,567 ha"]
    assert stated.value == pytest.approx(1234.567)
    assert stated.other is None


def test_the_reply_mark_is_inferred_from_grouping():
    # "12.802.558" groups with dots, so the comma is the reply's decimal mark.
    stated = _local("12.802.558 ha y luego 86.890 ha", "es")["86.890 ha"]
    assert stated.value == 86890
    assert stated.other.value == pytest.approx(86.89)
    alone = _local("solo 86.890 ha", "es")["86.890 ha"]
    assert alone.value == pytest.approx(86.89)
    assert alone.other.value == 86890


@pytest.mark.parametrize(
    ("language", "lead", "number", "value"),
    [
        *(("es", f"Al {date} se perdieron", "1.209 ha", 1.209)
          for date in ("31.12.2024", "2.1.0", "1.23.4567")),
        *(("id", f"{aside}:", "1.209 hektar", 1209)
          for aside in ("pukul 10.30 WIB", "Landsat 8.2", "di -3.45, 102.3",
                        "Menurut GADM 4.1, kehilangan tutupan pohon adalah")),
    ],
)
def test_dates_versions_and_coordinates_are_not_evidence_of_the_reply_mark(
    language, lead, number, value
):
    stated = _local(f"{lead} {number}.", language)[number]
    assert stated.value == pytest.approx(value)
    if language == "es":
        assert stated.other.value == 1209


def test_grouping_must_be_in_threes():
    assert stated_numbers("1.23.4567 ha", "es") == []
    assert stated_numbers("1,23,4567 ha", "id") == []


def test_a_year_with_a_unit_or_percent_is_a_figure():
    assert "2024" not in _local("en 2024 hubo", "es")
    assert _local("unas 2024 ha", "es")["2024 ha"].value == 2024
    assert _local("un 2024%", "es")["2024%"].percent


def test_scale_words_belong_to_their_language():
    assert _local("2 miles de millones de ha", "es")["2 miles de millones"].value == 2e9
    assert _local("5 mil hectáreas", "id")["5"].value == 5
    assert _local("5 ribu hektar", "es")["5"].value == 5
    assert _local("450 rb hektar", "id")["450 rb"].value == 450e3


def test_portuguese_scales_are_brazilian():
    # AJ, 2026-11-19: Brazilian Portuguese. The European "bilião" (10^12 in
    # Portugal) is no scale at all, so it can never pass as 10^9.
    assert _local("1,2 bilhão de toneladas", "pt")["1,2 bilhão"].value == pytest.approx(1.2e9)
    stated = _local("1,2 bilião de toneladas", "pt")
    assert stated["1,2"].value == pytest.approx(1.2)
    assert _local("2 billion t", "pt")["2 billion"].value == pytest.approx(2e9)


def test_a_french_billion_is_ten_to_the_twelfth():
    # AJ, 2026-11-19: in a French reply "billion" has its French meaning.
    stated = _local("Les stocks atteignent 1,2 billion de tonnes de carbone.", "fr")
    assert stated["1,2 billion"].value == pytest.approx(1.2e12)
    assert _local("environ 2 billions de tonnes", "fr")["2 billions"].value == (
        pytest.approx(2e12)
    )


def test_the_usual_portuguese_and_french_mark_is_the_comma():
    # Nothing in these replies settles the mark, so Horizon's habit in the
    # language gives the first reading (see _USUAL_DECIMAL_MARK).
    for answer, language in (("Total de 64.435 hectares.", "pt"),
                             ("Au total, 64,435 hectares.", "fr")):
        (stated,) = stated_numbers(answer, language)
        assert stated.other is not None
        assert (stated.value, stated.other.value) == (
            pytest.approx(64435 if language == "pt" else 64.435),
            pytest.approx(64.435 if language == "pt" else 64435),
        )


def test_figure_match_abstains_on_a_number_that_reads_two_ways(pulled):
    figure = "sum(area_ha)"  # 1,050 over both areas

    def score(answer, language):
        state, tables = _state(answer, TCL)
        pulled(tables)
        return evaluate_figures(state, figure, language)

    assert score("Total: 1.050 hektar.", "id")["figure_match_score"] == 1.0
    assert score("Total: 1,050 hectáreas.", "es")["figure_match_score"] == 1.0
    # Horizon's Spanish replies mostly write 1,050; "1.050" alone reads as
    # 1.05 first, and 1,050 is only its second reading.
    unsure = score("Total: 1.050 hectáreas.", "es")
    assert unsure["figure_match_score"] is None
    assert "reads two ways" in unsure["figure_match_reason"]
    # "1,05 kha" shows the reply's decimal mark, so "1.050" is 1,050.
    settled = score("Total: 1.050 hectáreas (1,05 kha).", "es")
    assert settled["figure_match_score"] == 1.0
    state, tables = _state(
        "Pico de **16,08 millones de hectáreas** en 2017; pérdida neta de unas"
        " **8,374 hectáreas**.",
        [{"aoi_id": "X", "tree_cover_loss_year": 2020, "area_ha": 8374.0}],
    )
    pulled(tables)
    assert evaluate_figures(state, "sum(area_ha)", "es")["figure_match_score"] is None
    # A clear number elsewhere does not turn the other reading into a fail.
    mixed = "Pico de **16,08 millones de hectáreas** en 2017; unas **1,050 hectáreas**."
    assert score(mixed, "es")["figure_match_score"] is None
    state, tables = _state("### 1.1 Ringkasan\nTotal kehilangan 64.435 hektar.", [
        {"aoi_id": "X", "tree_cover_loss_year": 2020, "area_ha": 64435.0}])
    pulled(tables)
    # A section number ("1.1") is no evidence of the reply's mark, so the
    # Indonesian habit reads "64.435" as 64435.
    assert evaluate_figures(state, "sum(area_ha)", "id")["figure_match_score"] == 1.0
    assert score("Total: 2.345 hectáreas.", "es")["figure_match_score"] == 0.0
    # Portuguese and French: the comma is the usual decimal mark.
    assert score("Total de 1.050 hectares.", "pt")["figure_match_score"] == 1.0
    assert score("Au total, 1 050 hectares.", "fr")["figure_match_score"] == 1.0
    assert score("Total de 1,050 hectares.", "pt")["figure_match_score"] is None
    assert score("Au total, 1,050 hectares.", "fr")["figure_match_score"] is None
    # An English reply to either keeps the English habit.
    english = "In total, the loss was 1,050 hectares in the area over the period."
    for language in ("pt", "fr"):
        assert score(english, language)["figure_match_score"] == 1.0
    assert score("Au total, 2 345 hectares.", "fr")["figure_match_score"] == 0.0


def test_a_zero_figure_may_be_stated_in_local_words(pulled):
    empty_year = [{"aoi_id": "BRA1507", "tree_cover_loss_year": 2021, "area_ha": 0.0}]
    for answer, language in [
        ("No se registró ninguna pérdida en el territorio.", "es"),
        ("Tidak ada kehilangan tutupan pohon di wilayah ini.", "id"),
        ("No loss was recorded in the territory.", "id"),
        ("No se han registrado alertas ni perdida de bosque.", "es"),
        ("No hay cambios en la cobertura.", "es"),
        ("Tidak ditemukan adanya kehilangan tutupan pohon.", "id"),
        ("Belum ada peringatan di wilayah ini.", "id"),
        ("Se mantiene en cero alertas este año.", "es"),
        ("Se reportaron cero hectáreas de pérdida.", "es"),
        ("No se registro\u0301 ninguna pe\u0301rdida.", "es"),
    ]:
        state, tables = _state(answer, empty_year)
        pulled(tables)
        result = evaluate_figures(state, figure_text="sum(area_ha)", language=language)
        assert result["figure_match_score"] == 1.0, answer
    # Sentences that use a zero word but do not state a zero figure.
    for answer, language in [
        ("La meta es deforestación cero; sin embargo las alertas aumentaron.", "es"),
        ("Más que en ningún otro año; sin datos de pérdida para 2021.", "es"),
        ("Komitmen emisi nol bersih; tidak ada data kehilangan.", "id"),
        ("Dihitung tanpa memperhitungkan emisi.", "id"),
        ("Hay un compromiso de cero deforestación en la región.", "es"),
        ("El objetivo es cero emisiones netas.", "es"),
        ("Hubo niveles sin precedentes de pérdida.", "es"),
        ("Sin información de pérdida para 2021.", "es"),
        ("No hay información sobre pérdidas.", "es"),
        ("Sin duda la pérdida fue grande.", "es"),
        ("Se vigila sin importar las alertas.", "es"),
        ("Sin contar la pérdida de 2020.", "es"),
        ("Sin incluir alertas de 2021.", "es"),
        ("Tidak ada informasi kehilangan.", "id"),
    ]:
        state, tables = _state(answer, empty_year)
        pulled(tables)
        result = evaluate_figures(state, figure_text="sum(area_ha)", language=language)
        assert result["figure_match_score"] == 0.0, answer


def test_local_zero_phrases_need_the_measured_noun_at_once(pulled):
    empty_year = [{"aoi_id": "BRA1507", "tree_cover_loss_year": 2021, "area_ha": 0.0}]

    def score(sentence, language):
        lead = "La cifra es de 120 ha. " if language == "es" else "Angkanya 120 ha. "
        state, tables = _state(lead + sentence, empty_year)
        pulled(tables)
        result = evaluate_figures(state, figure_text="sum(area_ha)", language=language)
        return result["figure_match_score"]

    # The negation or "without" belongs to another clause: no zero is stated.
    for sentence, language in [
        ("La pérdida fue de 120 ha, sin distinguir las pérdidas por causa.", "es"),
        ("Estos datos no permiten distinguir las pérdidas por causa.", "es"),
        ("La pérdida de cobertura arbórea no es deforestación.", "es"),
        ("El conjunto de datos no proporciona alertas en tiempo real.", "es"),
        ("No hubo reducción de las pérdidas respecto a 2020.", "es"),
        ("No hubo reducción de pérdidas respecto a 2020.", "es"),
        ("No hubo aumento de alertas respecto a 2020.", "es"),
        ("No hubo cambio en las pérdidas respecto a 2020.", "es"),
        ("sin considerar las pérdidas por incendios", "es"),
        ("sin incluir las alertas de baja confianza", "es"),
        ("sin distinguir pérdidas por causa", "es"),
        ("tanpa membedakan kehilangan berdasarkan penyebab", "id"),
        ("Data ini tidak dapat membedakan kehilangan berdasarkan penyebab.", "id"),
        ("tidak termasuk peringatan berkepercayaan rendah", "id"),
        ("Tidak ada penurunan kehilangan dibandingkan 2020", "id"),
        ("Tidak ada peningkatan kehilangan dibandingkan 2020", "id"),
        ("Tidak ada perubahan kehilangan dibandingkan 2020", "id"),
    ]:
        assert score(sentence, language) == 0.0, sentence
    # A real zero statement still counts.
    for sentence, language in [
        ("No hubo pérdida de cobertura arbórea en 2021.", "es"),
        ("No se detectaron alertas en este periodo.", "es"),
        ("No se registró ninguna pérdida.", "es"),
        ("No se detectó ninguna nueva alerta.", "es"),
        ("Sin alertas en el periodo.", "es"),
        ("Sin ninguna alerta en el periodo.", "es"),
        ("No hay cambios en la cobertura.", "es"),
        ("Tidak ada kehilangan tutupan pohon pada tahun 2021.", "id"),
        ("Tidak ada peringatan yang terdeteksi.", "id"),
        ("Tidak ditemukan adanya kehilangan tutupan pohon.", "id"),
        ("Tanpa peringatan pada periode ini.", "id"),
    ]:
        assert score(sentence, language) == 1.0, sentence


def test_an_unknown_language_is_loud_even_when_nothing_is_scored():
    with pytest.raises(ValueError, match="language"):
        evaluate_figures({}, "", "de")
    with pytest.raises(ValueError, match="language"):
        evaluate_figures({}, "sum(area_ha)", "de")


def test_figure_match_passes_rounding_and_fails_a_wrong_figure(pulled):
    figure = "sum(area_ha) where tree_cover_loss_year in 2018..2021"
    state, tables = _state("Loss totalled about 1,050 hectares.", TCL)
    pulled(tables)
    result = evaluate_figures(state, figure)
    assert result["figure_match_score"] == 1.0  # both areas: 1,000 + 50
    state, tables = _state("Loss totalled 1,250 hectares.", TCL)
    pulled(tables)
    result = evaluate_figures(state, figure)
    assert result["figure_match_score"] == 0.0
    assert "not in the reply" in result["actual_figures"]


def test_figure_match_abstains_without_a_readable_pull(pulled):
    state, tables = _state("1,000 ha", TCL)
    pulled({})
    assert evaluate_figures(state, "sum(area_ha)")["figure_match_score"] is None
    pulled(tables)
    assert evaluate_figures(state, "sum(other_column)")["figure_match_score"] is None


def test_shares_match_as_a_fraction_or_a_percentage(pulled):
    share = "ratio(sum(area_ha) where aoi_id = 'PER.23', sum(area_ha))"  # 4.76%
    for answer, score in [("about 4.8% of the loss", 1.0), ("a share of 0.048", 1.0),
                          ("about 9% of the loss", 0.0)]:
        state, tables = _state(answer, TCL)
        pulled(tables)
        assert evaluate_figures(state, share)["figure_match_score"] == score, answer


def test_a_comparison_split_over_two_pulls_uses_their_union(pulled):
    first = [r for r in TCL if r["aoi_id"] == "PER.12"]
    second = [r for r in TCL if r["aoi_id"] == "PER.23"]
    state, tables = _state("PER.12 lost 1,000 ha and PER.23 lost 50 ha.", first, second)
    pulled(tables)
    figure = "sum(area_ha) where aoi_id = 'PER.12' ; sum(area_ha) where aoi_id = 'PER.23'"
    assert evaluate_figures(state, figure)["figure_match_score"] == 1.0


# ---------------------------------------------------------------- the claim


def test_the_data_picks_the_claim_sentence(pulled):
    state, tables = _state("", TCL)
    pulled(tables)
    figure = ("sum(area_ha) where tree_cover_loss_year = 2021 ; "
              "ref: max(area_ha) by tree_cover_loss_year where tree_cover_loss_year in 2018..2020")
    sentence, detail = claim_sentence(state, figure, "#1 > #2 :: 2021 was the record || not")
    assert sentence == "2021 was the record"
    assert "is True" in detail
    assert parse_claim("#1 < 0 :: sink || source", 1).op == "<"


def test_figure_claim_is_judged_on_the_true_sentence(pulled, monkeypatch):
    seen = {}

    def judge(sentence, answer):
        seen["sentence"] = sentence
        return {"score": 1, "reason": "it says so"}

    monkeypatch.setattr("goldset.evaluators.llm_judges.llm_judge_claim", judge)
    state, tables = _state("2021 was the worst year.", TCL)
    pulled(tables)
    result = evaluate_figure_claim(
        state, "sum(area_ha) where tree_cover_loss_year = 2021 ; ref: sum(area_ha)",
        "#1 > #2 :: one year is more than all || one year is not more than all",
    )
    assert seen["sentence"] == "one year is not more than all"
    assert result["figure_claim_match_score"] == 1.0


# ----------------------------------------------------------------- the period


def test_answer_period_reads_the_period_and_maps_the_verdict(monkeypatch):
    seen = {}

    def judge(query, period, answer, fixed_period=""):
        seen["period"] = period
        seen["fixed_period"] = fixed_period
        return {"verdict": "fail", "reason": "it averaged 2001 to 2025"}

    monkeypatch.setattr("goldset.evaluators.llm_judges.llm_judge_answer_period", judge)
    state = {"messages": [SimpleNamespace(content="The average was 1.2 Mha.")]}
    result = evaluate_answer_period(state, "Average 2018-2022?", "2018-01-01", "2022-12-31")
    assert seen["period"] == "from 2018 to 2022"
    assert seen["fixed_period"] == ""
    assert result["answer_period_match_score"] == 0.0
    open_ended = evaluate_answer_period(state, "Since 2021?", "2021-01-01", "")
    assert seen["period"] == "from 2021 to the latest data available"
    assert open_ended["answer_period_match_score"] == 0.0
    assert evaluate_answer_period(state, "q", "", "")["answer_period_match_score"] is None


def test_answer_period_passes_a_fixed_period_to_the_judge(monkeypatch):
    # ch-causal-015: drivers data only come as 2001 to 2025 as a whole
    seen = {}

    def judge(query, period, answer, fixed_period=""):
        seen["fixed_period"] = fixed_period
        return {"verdict": "pass", "reason": "2001 to 2025, stated as the data's period"}

    monkeypatch.setattr("goldset.evaluators.llm_judges.llm_judge_answer_period", judge)
    state = {"messages": [SimpleNamespace(content="Agriculture: 227,084 ha (2001-2025).")]}
    result = evaluate_answer_period(
        state, "Fires or agriculture, 2015-2023?", "2015-01-01", "2023-12-31", 0, "2001-2025"
    )
    assert seen["fixed_period"] == "2001 to 2025"
    assert result["answer_period_match_score"] == 1.0
    with pytest.raises(ValueError, match="YYYY-YYYY"):
        evaluate_answer_period(state, "q", "2015-01-01", "2023-12-31", 0, "2001 to 2025")


def test_answer_period_not_applicable_scores_null(monkeypatch):
    monkeypatch.setattr(
        "goldset.evaluators.llm_judges.llm_judge_answer_period",
        lambda q, p, a, f="": {"verdict": "not_applicable", "reason": "it declined"},
    )
    state = {"messages": [SimpleNamespace(content="I cannot answer that.")]}
    result = evaluate_answer_period(state, "q", "{run-14d}" and "2026-10-13", "2026-10-27", 3)
    assert result["answer_period_match_score"] is None


def test_a_zero_figure_may_be_stated_in_words(pulled):
    # Kayapó (BRA1507) returns no loss: "no loss was recorded" states it.
    empty_year = [{"aoi_id": "BRA1507", "tree_cover_loss_year": 2021, "area_ha": 0.0}]
    state, tables = _state("No loss was recorded in the territory in 2021.", empty_year)
    pulled(tables)
    assert evaluate_figures(state, "sum(area_ha)")["figure_match_score"] == 1.0



@pytest.mark.parametrize("space", [" ", " ", " "])
def test_a_fixed_space_groups_thousands(space):
    (stated,) = stated_numbers(f"Se perdieron 1{space}209 ha.", "es")
    assert stated.value == 1209
    (stated,) = stated_numbers(f"Total 12{space}345{space}678 hektar.", "id")
    assert stated.value == 12345678


def test_a_plain_space_keeps_the_joined_number_and_its_parts():
    # "5 200 ha" may be one figure or a list, so neither reading hides the other.
    values = {s.text: s.value for s in stated_numbers("unas 5 200 ha", "es")}
    assert values == {"5 200 ha": 5200, "5": 5, "200 ha": 200}
    # The unit and percent belong to the last part and to the joined number.
    assert any(s.percent and s.value == 200 for s in stated_numbers("el 5 200 %", "es"))


def test_a_four_digit_head_is_not_grouping():
    values = [s.value for s in stated_numbers("en 2024 120 ha", "es")]
    assert values == [120]


def test_the_english_path_reads_a_spaced_number_as_before():
    # The unit slot takes "209", so only the 1 is a number: unchanged.
    assert [s.value for s in stated_numbers("1 209 ha")] == [1]
    assert [s.value for s in stated_numbers("1\u00a0209 ha")] == [1]


def test_a_spaced_figure_matches_in_either_reading(pulled):
    state, tables = _state("Se perdieron 1 050 hectáreas.", TCL)
    pulled(tables)
    assert evaluate_figures(state, "sum(area_ha)", "es")["figure_match_score"] == 1.0
    state, tables = _state("Quedan 3 050 hectáreas.", TCL)
    pulled(tables)
    assert evaluate_figures(state, "sum(area_ha)", "es")["figure_match_score"] == 0.0


def test_a_number_with_a_unit_or_percent_still_sets_the_reply_mark():
    # The comma is this Spanish reply's decimal mark, against the usual dot.
    stated = _local("10,46% y luego 321.221 hectáreas", "es")["321.221 hectáreas"]
    assert stated.value == 321221 and stated.other.value == pytest.approx(321.221)
    # Both marks, or grouping in threes, count without a unit.
    assert _local("1.209,32 y 5.100 ha", "es")["5.100 ha"].value == 5100
    assert _local("1.234.567 y 5.100 ha", "es")["5.100 ha"].value == 5100
    # A bare clear number ("12,5") is no longer enough: it may be a time.
    assert _local("a las 12,5 y 5.100 ha", "es")["5.100 ha"].value == pytest.approx(5.1)


def test_an_english_reply_to_a_local_case_uses_the_english_mark(pulled):
    state, tables = _state(
        "Tree cover loss was 1,209 hectares in the selected area during the year.",
        [{"aoi_id": "X", "tree_cover_loss_year": 2020, "area_ha": 1209.0}],
    )
    pulled(tables)
    for language in ("id", "es"):
        result = evaluate_figures(state, "sum(area_ha)", language)
        assert result["figure_match_score"] == 1.0, language
    # The public reader still follows the case language unless told.
    (stated,) = stated_numbers("Se perdieron 1,209 hectáreas.", "es")
    assert stated.value == 1209
    (stated,) = stated_numbers("Hilang 1,209 hektar.", "id")
    assert stated.value == pytest.approx(1.209)
    (stated,) = stated_numbers("Hilang 1,209 hektar.", "id", usual_mark=".")
    assert stated.value == 1209


def test_a_local_reply_keeps_the_case_languages_habit(pulled):
    state, tables = _state(
        "Kehilangan tutupan pohon adalah 1,209 hektar di area yang dipilih"
        " pada tahun tersebut.",
        [{"aoi_id": "X", "tree_cover_loss_year": 2020, "area_ha": 1209.0}],
    )
    pulled(tables)
    # Indonesian writes the comma as decimal, so 1209 is only the second reading.
    result = evaluate_figures(state, "sum(area_ha)", "id")
    assert result["figure_match_score"] is None

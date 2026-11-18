"""reply_language_match: does the final reply use the case's language?"""

from types import SimpleNamespace

import pytest

from goldset.evaluators.reply_language import (
    detect_language,
    evaluate_reply_language,
)

SPANISH = (
    "Según los datos de alertas, en el departamento de Ucayali se detectaron "
    "unas 12.480 hectáreas de perturbación entre enero y junio de 2026. La "
    "mayor parte de las alertas se concentra en la provincia de Coronel "
    "Portillo, y el ritmo es más alto que en el mismo periodo del año pasado."
)
# The dataset names, units and numbers stay in English, as Horizon writes them.
SPANISH_WITH_ENGLISH_NAMES = (
    "Usé el conjunto de datos **Tree cover loss by dominant driver** y también "
    "**Global all ecosystem alerts (DIST-ALERT)**. En Madre de Dios la pérdida "
    "fue de 1,234,567 ha entre 2015 y 2023, lo que equivale a 0.45 Mha por "
    "año. La causa principal es *Permanent agriculture* (62%), seguida de "
    "*Wildfire* (21%). Los datos provienen de Global Forest Watch: "
    "https://www.globalforestwatch.org/map/country/PER/ para más detalles."
)
INDONESIAN = (
    "Berdasarkan data peringatan, di Provinsi Riau terdapat sekitar 8.250 "
    "hektare gangguan hutan antara Januari dan Juni 2026. Sebagian besar "
    "peringatan tersebut berada di Kabupaten Pelalawan, dan angka ini lebih "
    "tinggi dari periode yang sama pada tahun lalu."
)
INDONESIAN_WITH_TABLE = (
    "Berikut adalah kehilangan tutupan pohon di Kalimantan Tengah untuk tiga "
    "tahun terakhir, yang dihitung dari data Tree cover loss:\n\n"
    "| Year | Loss (ha) | Share of the total |\n"
    "|---|---|---|\n"
    "| 2021 | 101,200 | 31% of the loss in the period |\n"
    "| 2022 | 98,450 | 30% of the loss in the period |\n"
    "| 2023 | 125,900 | 39% of the loss in the period |\n\n"
    "Angka tertinggi terjadi pada tahun 2023, dan sebagian besar kehilangan "
    "tersebut disebabkan oleh perluasan perkebunan."
)
ENGLISH = (
    "Based on the alerts data, there were about 12,480 hectares of disturbance "
    "in Ucayali between January and June 2026. Most of the alerts are in "
    "Coronel Portillo province, and the rate is higher than in the same "
    "period of last year."
)
# English prose about places whose names carry Spanish function words.
ENGLISH_WITH_SPANISH_PLACES = (
    "In Madre de Dios, the loss was 45,000 ha in 2023. That is more than in "
    "La Paz or in Santa Cruz de la Sierra, and it has been rising since 2019 "
    "in the areas that are close to the Interoceanic Highway."
)
PORTUGUESE = (
    "De acordo com os dados de alertas, no estado do Pará foram detectados "
    "cerca de 12.480 hectares de perturbação entre janeiro e junho de 2026. A "
    "maior parte dos alertas está no município de Altamira, e o ritmo é mais "
    "alto do que no mesmo período do ano passado."
)
MALAY = (
    "Berdasarkan data amaran, di negeri Sarawak terdapat kira-kira 8,250 "
    "hektar gangguan hutan antara Januari dan Jun 2026. Kebanyakan amaran "
    "tersebut berada di bahagian Kapit, dan angka ini lebih tinggi daripada "
    "tempoh yang sama pada tahun lepas kerana pembalakan."
)
HALF_AND_HALF = (
    "Según los datos, en el departamento de Ucayali se detectaron alertas "
    "entre enero y junio. The alerts are mostly in the east of the region, "
    "and the rate is higher than in the same period of last year."
)


def _state(text):
    return {"messages": [SimpleNamespace(content=text)]}


@pytest.mark.parametrize(("text", "language"), [
    (SPANISH, "es"),
    (SPANISH_WITH_ENGLISH_NAMES, "es"),
    (INDONESIAN, "id"),
    (INDONESIAN_WITH_TABLE, "id"),
    (ENGLISH, "en"),
    (ENGLISH_WITH_SPANISH_PLACES, "en"),
])
def test_detects_the_three_languages(text, language):
    assert detect_language(text)[0] == language


def test_a_table_does_not_vote():
    # The table's cells are English; the prose around it is Indonesian.
    _language, hits = detect_language(INDONESIAN_WITH_TABLE)
    assert hits["en"] == 0


def test_code_and_urls_do_not_vote():
    text = (
        "```python\nfor the in of: and is to with this that\n```\n"
        "`the of and to in is` https://example.org/the/of/and/to/in/is"
    )
    assert detect_language(text) == (None, {"en": 0, "es": 0, "id": 0})


@pytest.mark.parametrize("text", ["", "   \n", "Sí.", "Ya", "1,234 ha"])
def test_empty_and_one_word_replies_are_undecided(text):
    assert detect_language(text)[0] is None
    assert evaluate_reply_language(_state(text), "es")[
        "reply_language_match_score"
    ] is None


def test_a_reply_in_two_languages_is_undecided():
    language, hits = detect_language(HALF_AND_HALF)
    assert language is None
    assert hits["es"] and hits["en"]


def test_portuguese_reads_as_spanish_the_nearest_language():
    # Only en, es and id are told apart. Portuguese shares enough function
    # words with Spanish (de, que, se, por, entre) to read as Spanish.
    assert detect_language(PORTUGUESE)[0] == "es"


def test_malay_reads_as_indonesian_the_nearest_language():
    # Malay and Indonesian share their function words (di, dan, yang, pada).
    assert detect_language(MALAY)[0] == "id"


def test_scores_match_mismatch_and_undecided():
    match = evaluate_reply_language(_state(SPANISH), "es")
    assert match["reply_language_match_score"] == 1.0
    assert match["actual_reply_language"] == "es"

    wrong = evaluate_reply_language(_state(ENGLISH), "es")
    assert wrong["reply_language_match_score"] == 0.0
    assert wrong["actual_reply_language"] == "en"
    assert "en" in wrong["reply_language_match_reason"]

    undecided = evaluate_reply_language(_state(HALF_AND_HALF), "es")
    assert undecided["reply_language_match_score"] is None
    assert undecided["actual_reply_language"] is None
    assert "undecided" in undecided["reply_language_match_reason"]


def test_english_cases_are_scored_too():
    assert evaluate_reply_language(_state(ENGLISH))[
        "reply_language_match_score"
    ] == 1.0
    assert evaluate_reply_language(_state(INDONESIAN), "en")[
        "reply_language_match_score"
    ] == 0.0


def test_no_messages_abstains():
    result = evaluate_reply_language({"messages": []}, "id")
    assert result["reply_language_match_score"] is None
    assert result["actual_reply_language"] is None


def test_a_decomposed_accent_still_counts():
    decomposed = SPANISH.replace("ú", "ú").replace("á", "á")
    assert detect_language(decomposed) == detect_language(SPANISH)


def test_an_unknown_case_language_fails_loudly():
    with pytest.raises(ValueError, match="language must be one of"):
        evaluate_reply_language(_state(SPANISH), "pt")

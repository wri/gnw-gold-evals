"""reply_language_match: does the final reply use the case's language?"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import benchmark_page as bp  # noqa: E402
import challenge_rollup as cr  # noqa: E402

from goldset.benchmark import load_benchmark  # noqa: E402
from goldset.buckets import (  # noqa: E402
    attempt_verdict,
    buckets_for,
    implied_checks,
    is_info_only,
    row_verdict,
    summarize_buckets,
)
from goldset.canonical import LANGUAGES  # noqa: E402
from goldset.cli import result_to_entry  # noqa: E402
from goldset.eval_types import ExpectedData  # noqa: E402
from goldset.eval_types import TestResult as Result  # noqa: E402
from goldset.evaluators.reply_language import (  # noqa: E402
    detect_language,
    evaluate_reply_language,
)
from goldset.registry import EVALUATORS  # noqa: E402
from goldset.runner.base import BaseTestRunner  # noqa: E402

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
# Modelled on Horizon's Portuguese and French replies (traces, 2026): the
# dataset names stay in English, as Horizon writes them.
PORTUGUESE_WITH_ENGLISH_NAMES = (
    "Usei o conjunto de dados **Tree cover loss by dominant driver** e também "
    "**Global all ecosystem alerts (DIST-ALERT)**. Em São Félix do Xingu a "
    "perda foi de 1.234.567 ha entre 2015 e 2023, o que equivale a 0,45 Mha "
    "por ano. A principal causa é *Permanent agriculture* (62%), seguida de "
    "*Wildfire* (21%). Os dados vêm do Global Forest Watch: "
    "https://www.globalforestwatch.org/map/country/BRA/ para mais detalhes."
)
FRENCH_WITH_ENGLISH_NAMES = (
    "J'ai utilisé le jeu de données **Tree cover loss by dominant driver** et "
    "**Integrated deforestation alerts**. Dans la région de l'Est, la perte a "
    "atteint 12 480 ha en 2023. La cause principale est *Shifting "
    "cultivation* (71 %), suivie de *Logging* (18 %). Les données proviennent "
    "de Global Forest Watch : https://www.globalforestwatch.org/map/country/CMR/"
)
# English prose about places whose names carry Portuguese function words.
ENGLISH_WITH_BRAZILIAN_PLACES = (
    "In São Félix do Xingu, the loss was 45,000 ha in 2023. That is more than "
    "in Mato Grosso do Sul or in Rio de Janeiro, and it has been rising since "
    "2019 in the areas that are close to the BR-163 highway."
)
# Short replies (a clarifying question) carry few function words, and the
# Romance languages share many of them.
SHORT_SPANISH = (
    "Encontré dos áreas con el nombre Santa María: una en Chubut y otra en "
    "Catamarca. ¿Cuál de ellas quieres analizar?"
)
SHORT_PORTUGUESE = (
    "Encontrei duas áreas com o nome Santa Maria: uma no Rio Grande do Sul e "
    "outra no Pará. Qual delas você quer analisar?"
)
SHORT_FRENCH = (
    "J'ai trouvé deux zones nommées Saint-Laurent : l'une au Québec et l'autre "
    "en Guyane. Laquelle voulez-vous analyser ?"
)
MALAY = (
    "Berdasarkan data amaran, di negeri Sarawak terdapat kira-kira 8,250 "
    "hektar gangguan hutan antara Januari dan Jun 2026. Kebanyakan amaran "
    "tersebut berada di bahagian Kapit, dan angka ini lebih tinggi daripada "
    "tempoh yang sama pada tahun lepas kerana pembalakan."
)
FRENCH = (
    "Selon les données d'alertes, dans le département de l'Ucayali, environ "
    "12 480 hectares de perturbation ont été détectés entre janvier et juin "
    "2026. La plupart des alertes se trouvent dans la province de Coronel "
    "Portillo, et le rythme est plus élevé que pendant la même période de "
    "l'année dernière."
)
# Modelled on Horizon's Italian replies (traces, 2026).
ITALIAN = (
    "Ho analizzato i dati sulla perdita di copertura arborea nella regione "
    "della Toscana dal 2001 al 2024. La perdita totale è stata di circa "
    "12.480 ettari, e la maggior parte degli eventi si concentra nelle "
    "province di Grosseto e di Arezzo. Il ritmo è più alto negli ultimi "
    "anni, anche a causa degli incendi."
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
    (PORTUGUESE, "pt"),
    (PORTUGUESE_WITH_ENGLISH_NAMES, "pt"),
    (FRENCH, "fr"),
    (FRENCH_WITH_ENGLISH_NAMES, "fr"),
    (ENGLISH, "en"),
    (ENGLISH_WITH_SPANISH_PLACES, "en"),
    (ENGLISH_WITH_BRAZILIAN_PLACES, "en"),
    (SHORT_SPANISH, "es"),
    (SHORT_PORTUGUESE, "pt"),
    (SHORT_FRENCH, "fr"),
])
def test_detects_each_case_language(text, language):
    assert detect_language(text)[0] == language


def test_a_leader_with_no_word_of_its_own_is_undecided():
    # Every word it counts is one French also lists, so French only came first
    # by listed order: the reply is no evidence of either language.
    text = "A perda a partir daquele ano chegou a 120 ha, segundo a análise."
    assert detect_language(text)[0] is None


def test_a_table_does_not_vote():
    # The table's cells are English; the prose around it is Indonesian.
    _language, hits = detect_language(INDONESIAN_WITH_TABLE)
    assert hits["en"] == 0


def test_code_and_urls_do_not_vote():
    text = (
        "```python\nfor the in of: and is to with this that\n```\n"
        "`the of and to in is` https://example.org/the/of/and/to/in/is"
    )
    assert detect_language(text) == (
        None, {"en": 0, "es": 0, "id": 0, "fr": 0, "pt": 0, "it": 0}
    )


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


def test_portuguese_and_french_are_told_apart_from_spanish():
    assert detect_language(PORTUGUESE)[0] == "pt"
    assert detect_language(FRENCH)[0] == "fr"


def test_italian_is_told_apart_from_french_and_spanish():
    # Without its own list an Italian reply reads as French ("la", "il", "a").
    assert detect_language(ITALIAN)[0] == "it"


def test_malay_reads_as_indonesian_the_nearest_language():
    # Malay and Indonesian share their function words (di, dan, yang, pada).
    assert detect_language(MALAY)[0] == "id"


@pytest.mark.parametrize(("text", "language"), [
    (ENGLISH, "en"), (SPANISH, "es"), (INDONESIAN, "id"), (PORTUGUESE, "pt"),
    (FRENCH, "fr"), (SHORT_SPANISH, "es"), (SHORT_PORTUGUESE, "pt"),
    (SHORT_FRENCH, "fr"),
])
def test_a_reply_scores_one_in_its_language_and_zero_in_every_other(text, language):
    # Spanish, Portuguese and French share many function words: a reply in
    # one of them must still score 0.0 for a case in another.
    assert language in LANGUAGES
    for case_language in LANGUAGES:
        result = evaluate_reply_language(_state(text), case_language)
        assert result["actual_reply_language"] == language
        assert result["reply_language_match_score"] == (
            1.0 if case_language == language else 0.0
        ), case_language


def test_an_italian_reply_scores_zero_against_every_language():
    for case_language in LANGUAGES:
        result = evaluate_reply_language(_state(ITALIAN), case_language)
        assert result["reply_language_match_score"] == 0.0
        assert result["actual_reply_language"] == "it"


def test_a_decoy_is_never_a_case_language():
    with pytest.raises(ValueError, match="language must be one of"):
        evaluate_reply_language(_state(ITALIAN), "it")


def test_a_spanish_query_on_an_unlabelled_case_is_not_scored():
    query = "¿Cuánta cobertura arbórea se perdió en el departamento de Ucayali?"
    result = evaluate_reply_language(_state(SPANISH), "en", query)
    assert result["reply_language_match_score"] is None
    assert "query reads as es" in result["reply_language_match_reason"]
    assert result["actual_reply_language"] == "es"
    # An English query, or one too short to read, keeps the English rule.
    english = "How much tree cover was lost in the department of Ucayali?"
    assert evaluate_reply_language(_state(SPANISH), "en", english)[
        "reply_language_match_score"
    ] == 0.0
    assert evaluate_reply_language(_state(SPANISH), "en", "Ucayali?")[
        "reply_language_match_score"
    ] == 0.0
    # A labelled case is scored whatever its query.
    assert evaluate_reply_language(_state(SPANISH), "es", query)[
        "reply_language_match_score"
    ] == 1.0


def test_the_runner_passes_the_query_to_the_check():
    class Probe(BaseTestRunner):
        async def run_test(self, query, expected_data):  # pragma: no cover
            raise NotImplementedError

    query = "¿Cuánta cobertura arbórea se perdió en el departamento de Ucayali?"
    evaluations = Probe()._run_evaluations(
        _state(SPANISH), ExpectedData(), query, None
    )
    assert evaluations[f"{CHECK}_score"] is None


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


# --- wiring: registered for every case, info-only, never part of a verdict ---

CHECK = "reply_language_match"
GATING_PASS = {"aoi_id_match": 1.0, "dataset_id_match": 1.0}
GATING_FAIL = {"aoi_id_match": 0.0, "dataset_id_match": 1.0}


def _entry(*trials):
    if len(trials) == 1:
        return {"uid": "u", "id": "c", "checks": dict(trials[0])}
    final = {
        name: 1.0 if sum(t[name] == 1.0 for t in trials) * 2 > len(trials) else 0.0
        for name in trials[0]
    }
    return {"uid": "u", "id": "c", "checks": final,
            "trials": [{"checks": dict(t)} for t in trials]}


def _with_wrong_language(entry):
    out = {**entry, "checks": {**entry["checks"], CHECK: 0.0}}
    if "trials" in entry:
        out["trials"] = [
            {**t, "checks": {**t["checks"], CHECK: 0.0}} for t in entry["trials"]
        ]
    return out


ENTRIES = [
    _entry(GATING_PASS),
    _entry(GATING_FAIL),
    _entry({"aoi_id_match": None}),  # uncovered: the check must not cover it
    _entry(GATING_PASS, GATING_PASS, GATING_PASS),
    _entry(GATING_PASS, GATING_PASS, GATING_FAIL),
    _entry(GATING_FAIL, GATING_FAIL, GATING_PASS),
]


def test_registered_for_every_case_and_info_only():
    [spec] = [s for s in EVALUATORS if s.name == "reply_language"]
    assert spec.kind == "deterministic"
    assert spec.score_fields == (f"{CHECK}_score",)
    assert not spec.presumes_pull and not spec.presumes_area
    assert is_info_only(CHECK) and is_info_only(f"t2.{CHECK}")
    assert buckets_for(CHECK) == ()
    # It may abstain (a short or mixed reply), so no case implies it.
    assert CHECK not in implied_checks({"aoi_ids": "BRA", "answer": "1"})


def test_the_runner_scores_a_case_with_no_other_expectation():
    class Probe(BaseTestRunner):
        async def run_test(self, query, expected_data):  # pragma: no cover
            raise NotImplementedError

    for language, text, score in (("es", SPANISH, 1.0), ("en", SPANISH, 0.0)):
        evaluations = Probe()._run_evaluations(
            _state(text), ExpectedData(language=language), "q", None
        )
        assert evaluations[f"{CHECK}_score"] == score
        assert evaluations["judge_errors"] == []


@pytest.mark.parametrize("entry", ENTRIES)
def test_a_wrong_language_changes_no_verdict(entry):
    wrong = _with_wrong_language(entry)
    assert row_verdict(wrong) == row_verdict(entry)
    assert cr.strict_clean(wrong) == cr.strict_clean(entry)
    assert cr.primary_failure(wrong) == cr.primary_failure(entry)
    for before, after in zip(entry.get("trials", []), wrong.get("trials", [])):
        assert attempt_verdict(after) == attempt_verdict(before)
        assert bp.trial_ok(after) == bp.trial_ok(before)


def test_a_wrong_language_changes_no_rate_or_bucket():
    wrong = [_with_wrong_language(e) for e in ENTRIES]
    assert summarize_buckets(wrong) == summarize_buckets(ENTRIES)
    three_trial = [e for e in ENTRIES if "trials" in e]
    assert bp.group_stats([_with_wrong_language(e) for e in three_trial]) == (
        bp.group_stats(three_trial)
    )
    assert bp.failed_checks(_with_wrong_language(three_trial[-1])) == (
        bp.failed_checks(three_trial[-1])
    )


def test_the_ledger_keeps_the_detected_language_of_a_wrong_reply():
    evaluation = evaluate_reply_language(_state(ENGLISH), "es")
    result = Result(
        thread_id="t", query="q", overall_score=0.0, execution_time="now",
        **evaluation,
    )
    entry = result_to_entry(result, "u")
    assert entry["checks"][CHECK] == 0.0
    assert entry["actuals"][CHECK] == "en"
    assert entry["reasons"][CHECK].startswith("en (function words: en ")


def test_committed_runs_without_the_check_still_read():
    # Runs recorded before the check have no such key anywhere; a missing
    # check is a null, so every reader takes them as before.
    # Pinned: "newest run" breaks as soon as a run records the check.
    path = ROOT / "results/benchmark/runs/20261028T124051Z_prod.json"
    run = json.loads(path.read_text(encoding="utf-8"))
    assert all(CHECK not in e.get("checks", {}) for e in run["results"])
    bench = load_benchmark(ROOT / run["benchmark"]["path"])
    rollup = cr.rollup_benchmark(run, bench)
    assert rollup["run_id"] == run["run_id"]
    summary = summarize_buckets(run["results"])
    assert summary["rows_total"] == len(run["results"])
    assert sum(summary["verdicts"].values()) == len(run["results"])

"""Tests du rapprochement des bases — la partie où une erreur ne se voit pas.

Une erreur de parsing finit en exception ; une erreur de matching finit en
tableau plausible et faux. D'où des tests sur les cas limites rencontrés
réellement dans les données.
"""
from __future__ import annotations

import pandas as pd
import pytest

from lobbynomics import config
from lobbynomics.matching import (
    extraire_denomination,
    nomme_le_texte,
    precision_par_niveau,
    rattacher_scrutins,
    taux_erreur,
)
from lobbynomics.parse_an import _liste, _txt, nettoyer_html, normaliser


# --------------------------------------------------------------------------
# Lecture du JSON « à la mode Assemblée »
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("entree", "attendu"), [
    ("PA793158", "PA793158"),
    ({"#text": "PA793158"}, "PA793158"),
    ({"@xsi:nil": "true"}, None),
    ("   ", None),
    (None, None),
])
def test_txt_gere_les_trois_formes(entree, attendu):
    assert _txt(entree) == attendu


def test_liste_normalise_zero_un_ou_n():
    assert _liste(None) == []
    assert _liste({"@xsi:nil": "true"}) == []
    assert _liste({"a": 1}) == [{"a": 1}]
    assert _liste([1, 2]) == [1, 2]


def test_nettoyer_html_gere_le_double_echappement():
    brut = "<p>À l&#x2019;alin&#x00E9;a&nbsp;2, substituer&nbsp;:</p>"
    assert nettoyer_html(brut) == "À l'alinéa 2, substituer :"


def test_normaliser_retire_accents_et_ponctuation():
    assert normaliser("Projet de loi d’urgence (1ère lecture).") == \
        "projet de loi d urgence 1ere lecture"


# --------------------------------------------------------------------------
# Extraction de la dénomination d'un texte dans un titre de scrutin
# --------------------------------------------------------------------------


def test_extraire_denomination_amendement():
    titre = ("l'amendement n° 1 du Gouvernement à l'article 4 bis A de la proposition "
             "de loi visant à sortir la France du piège du narcotrafic (première lecture).")
    assert extraire_denomination(titre) == "visant a sortir la france du piege du narcotrafic"


def test_extraire_denomination_prend_la_derniere_amorce():
    """« l'amendement … du projet de loi X » : la dénomination suit la dernière amorce."""
    titre = ("l'article 2 de la proposition de loi relative au sport, puis du projet "
             "de loi de finances rectificative (nouvelle lecture).")
    assert extraire_denomination(titre).startswith("de finances rectificative")


def test_extraire_denomination_sans_texte_identifiable():
    assert extraire_denomination("l'ensemble du texte.") == ""
    assert extraire_denomination(None) == ""


# --------------------------------------------------------------------------
# Rattachement scrutin -> dossier, et l'arbitrage par date
# --------------------------------------------------------------------------


@pytest.fixture
def dossiers_homonymes() -> pd.DataFrame:
    """Deux dossiers au titre identique : le cas qui faisait chuter la précision."""
    return pd.DataFrame([
        {"dossier_ref": "D_ANCIEN", "titre": "Nationalisation d'ArcelorMittal France",
         "date_premier_acte": "2025-06-04", "date_dernier_acte": "2025-07-01"},
        {"dossier_ref": "D_RECENT", "titre": "Nationalisation d'ArcelorMittal France",
         "date_premier_acte": "2026-05-01", "date_dernier_acte": "2026-07-01"},
    ])


def _scrutin(date: str) -> pd.DataFrame:
    return pd.DataFrame([{
        "scrutin_uid": "S1", "date_scrutin": date,
        "titre": ("l'amendement n° 190 après l'article 2 de la proposition de loi visant "
                  "à la nationalisation d'ArcelorMittal France (première lecture)."),
        "dossier_ref_declare": None,
    }])


def test_rattachement_choisit_le_dossier_contemporain(dossiers_homonymes):
    resultat = rattacher_scrutins(_scrutin("2026-06-11"), dossiers_homonymes)
    assert resultat.loc[0, "dossier_fuzzy"] == "D_RECENT"
    assert resultat.loc[0, "n_candidats_ex_aequo"] == 2


def test_rattachement_choisit_l_autre_dossier_si_le_scrutin_est_plus_ancien(dossiers_homonymes):
    resultat = rattacher_scrutins(_scrutin("2025-06-20"), dossiers_homonymes)
    assert resultat.loc[0, "dossier_fuzzy"] == "D_ANCIEN"


def test_le_lien_declare_prime_sur_le_fuzzy(dossiers_homonymes):
    scrutins = _scrutin("2026-06-11")
    scrutins["dossier_ref_declare"] = "D_ANCIEN"
    resultat = rattacher_scrutins(scrutins, dossiers_homonymes)
    assert resultat.loc[0, "dossier_ref"] == "D_ANCIEN"
    assert resultat.loc[0, "origine_lien"] == "declare"


def test_aucun_rattachement_sous_le_seuil(dossiers_homonymes):
    scrutins = _scrutin("2026-06-11")
    scrutins["titre"] = "l'amendement n° 3 du projet de loi relatif aux transports ferroviaires."
    resultat = rattacher_scrutins(scrutins, dossiers_homonymes)
    assert resultat.loc[0, "origine_lien"] == "aucun"
    assert pd.isna(resultat.loc[0, "dossier_ref"])


# --------------------------------------------------------------------------
# Ciblage HATVP : la règle de nommage doit rester étroite
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("cle", "objet", "attendu"), [
    ("defense", "lpm 2024 2030 et plf 2026 defendre la sanctuarisation", True),
    ("agriculture", "defendre les loups dans le cadre de la loi d urgence agricole", True),
    ("fraudes", "pjl fraudes sociales et fiscales renforcer le dispositif", True),
    # Le piège : des mots du titre présents, mais sur un tout autre véhicule.
    ("defense", "plfss demander la preservation de l acces aux traitements", False),
    ("agriculture", "plf 2026 maintenir le budget dedie aux aides a l agriculture", False),
    ("fraudes", "limiter la baisse des ressources publiques affectees au reseau des cci", False),
    ("agriculture", "", False),
])
def test_nomme_le_texte_reste_etroit(cle, objet, attendu):
    assert nomme_le_texte(objet, config.TEXTES_PAR_CLE[cle]) is attendu


# --------------------------------------------------------------------------
# Comptabilité de l'audit
# --------------------------------------------------------------------------


@pytest.fixture
def audit_factice() -> pd.DataFrame:
    return pd.DataFrame({
        "niveau_ciblage": ["1 - texte nommé"] * 3 + ["2 - voisinage thématique"] * 3,
        "cible_nommee": [True, True, True, False, False, False],
        "cible_texte": [True, True, True, False, False, False],
        "verdict_manuel": ["oui", "oui", "non", "oui", "non", "incertain"],
    })


def test_taux_erreur_ignore_les_incertains(audit_factice):
    mesures = taux_erreur(audit_factice, colonne="cible_nommee")
    assert mesures["n_annote"] == 5          # l'incertain est exclu
    assert mesures["n_incertain"] == 1
    assert mesures["vp"] == 2 and mesures["fp"] == 1 and mesures["fn"] == 1
    assert mesures["precision"] == pytest.approx(2 / 3)
    assert mesures["rappel"] == pytest.approx(2 / 3)


def test_precision_par_niveau(audit_factice):
    table = precision_par_niveau(audit_factice)   # arrondi à 3 décimales par la fonction
    assert table.loc["1 - texte nommé", "precision"] == pytest.approx(2 / 3, abs=1e-3)
    # Au niveau 2, un « oui », un « non », un « incertain » exclu du dénominateur.
    assert table.loc["2 - voisinage thématique", "precision"] == pytest.approx(1 / 2, abs=1e-3)


# --------------------------------------------------------------------------
# Déports : même piège de similarité partielle, même garde-fou
# --------------------------------------------------------------------------


@pytest.mark.parametrize(("reference", "attendu"), [
    ("Projet de loi n° 2630 actualisant la programmation militaire pour les années "
     "2024 à 2030", "actualisant la programmation militaire pour les annees 2024 a 2030"),
    ("Article 19 de la proposition de loi n°1100 relative à la fin de vie",
     "relative a la fin de vie"),
    # Référence générique : aucun texte identifiable, et c'est le bon résultat.
    ("Articles de loi ayant trait aux assurances et organismes complémentaires", ""),
    (None, ""),
])
def test_denomination_deport(reference, attendu):
    from lobbynomics.matching import denomination_deport
    assert denomination_deport(reference) == attendu


def test_denomination_deport_developpe_les_abreviations():
    from lobbynomics.matching import denomination_deport
    assert "financement de la securite sociale" in denomination_deport(
        "Article 7 du PLFSS pour 2026")


def test_rattachement_deport_refuse_un_titre_sans_rapport():
    """Le scorer partiel rattachait ces références à « Allocution du Président d'âge »."""
    from lobbynomics.matching import rattacher_deports
    dossiers = pd.DataFrame([
        {"dossier_ref": "D1", "titre": "Allocution du Président d'âge"},
        {"dossier_ref": "D2", "titre": "Fin de vie"},
    ])
    deports = pd.DataFrame([
        {"reference_textuelle": "Article 19 de la proposition de loi relative à la fin de vie",
         "reference_normalisee": "article 19 de la proposition de loi relative a la fin de vie"},
        {"reference_textuelle": "Articles de loi ayant trait aux assurances",
         "reference_normalisee": "articles de loi ayant trait aux assurances"},
    ])
    resultat = rattacher_deports(deports, dossiers)
    assert resultat.loc[0, "dossier_ref"] == "D2"
    assert pd.isna(resultat.loc[1, "dossier_ref"])

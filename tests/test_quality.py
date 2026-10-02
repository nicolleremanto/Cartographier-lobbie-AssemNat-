"""Tests des contrôles qualité.

Un contrôle qui ne sait pas détecter une anomalie fabriquée exprès ne détectera
pas non plus les vraies. Chaque test introduit donc volontairement le défaut que
le contrôle est censé repérer.
"""
from __future__ import annotations

import pandas as pd
import pytest

from lobbynomics import quality
from lobbynomics.quality import ALERTE, ECHEC, OK


@pytest.fixture
def amendements() -> pd.DataFrame:
    return pd.DataFrame([
        {"amendement_uid": "A1", "etat": "Discuté", "sort": "Adopté",
         "type_auteur": "Député", "acteur_ref": "PA1"},
        {"amendement_uid": "A2", "etat": "A discuter", "sort": None,
         "type_auteur": "Député", "acteur_ref": "PA2"},
        {"amendement_uid": "A3", "etat": "Discuté", "sort": "Rejeté",
         "type_auteur": "Gouvernement", "acteur_ref": None},
        {"amendement_uid": "A4", "etat": "effacé", "sort": None,
         "type_auteur": "Député", "acteur_ref": None},
    ])


def test_unicite_detecte_un_doublon():
    propre = pd.DataFrame({"uid": ["a", "b", "c"]})
    assert quality.unicite(propre, "uid", "t")["statut"] == OK
    doublon = pd.DataFrame({"uid": ["a", "a", "c"]})
    assert quality.unicite(doublon, "uid", "t")["statut"] == ECHEC


def test_unicite_detecte_un_identifiant_manquant():
    trou = pd.DataFrame({"uid": ["a", None, "c"]})
    assert quality.unicite(trou, "uid", "t")["statut"] == ECHEC


def test_integrite_detecte_les_cles_orphelines():
    parent = pd.DataFrame({"id": ["x", "y"]})
    enfant_ok = pd.DataFrame({"ref": ["x", "y", "x"]})
    assert quality.integrite(enfant_ok, "ref", parent, "id", "t")["statut"] == OK
    enfant_ko = pd.DataFrame({"ref": ["x", "z"]})
    assert quality.integrite(enfant_ko, "ref", parent, "id", "t")["statut"] == ECHEC


def test_integrite_tolere_une_faible_proportion():
    parent = pd.DataFrame({"id": [f"x{i}" for i in range(100)]})
    enfant = pd.DataFrame({"ref": [f"x{i}" for i in range(99)] + ["inconnu"]})
    assert quality.integrite(enfant, "ref", parent, "id", "t")["statut"] == ALERTE


def test_sort_et_etat_sont_coherents(amendements):
    assert quality.coherence_sort_etat(amendements)["statut"] == OK


def test_sort_sans_discussion_est_detecte(amendements):
    casse = amendements.copy()
    casse.loc[casse["amendement_uid"].eq("A2"), "sort"] = "Adopté"
    assert quality.coherence_sort_etat(casse)["statut"] == ECHEC


def test_auteur_absent_hors_gouvernement_est_detecte(amendements):
    """Les amendements effacés sont exclus ; un autre trou doit sortir en échec."""
    assert quality.coherence_auteur(amendements)["statut"] == OK
    casse = amendements.copy()
    casse.loc[casse["amendement_uid"].eq("A2"), "acteur_ref"] = None
    assert quality.coherence_auteur(casse)["statut"] == ECHEC


def test_dossiers_hors_legislature():
    dossiers = pd.DataFrame({"dossier_ref": ["DLR5L17N1"]})
    scrutins = pd.DataFrame({"dossier_ref": ["DLR5L17N1", "DLR5L16N9"]})
    assert quality.dossiers_hors_legislature(scrutins, dossiers)["statut"] == OK
    suspect = pd.DataFrame({"dossier_ref": ["DLR5L17N1", "INCONNU"]})
    assert quality.dossiers_hors_legislature(suspect, dossiers)["statut"] == ALERTE


def _scrutins_et_votes(n: int, n_en_ecart: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """n scrutins à 2 pour / 1 contre, dont `n_en_ecart` au détail nominatif décalé."""
    scrutins = pd.DataFrame({"scrutin_uid": [f"S{i}" for i in range(n)],
                             "nb_pour": [2] * n, "nb_contre": [1] * n})
    lignes = []
    for i in range(n):
        positions = (["pour", "contre", "contre"] if i < n_en_ecart
                     else ["pour", "pour", "contre"])
        for j, position in enumerate(positions):
            lignes.append({"scrutin_uid": f"S{i}", "acteur_ref": f"a{j}",
                           "position": position})
    return scrutins, pd.DataFrame(lignes)


def test_coherence_decomptes_sans_ecart():
    scrutins, votes = _scrutins_et_votes(10, 0)
    assert quality.coherence_decomptes(scrutins, votes)["statut"] == OK


def test_coherence_decomptes_ecart_modere_est_une_alerte():
    """Les mises au point de vote créent un écart attendu, pas une erreur."""
    scrutins, votes = _scrutins_et_votes(10, 2)
    assert quality.coherence_decomptes(scrutins, votes)["statut"] == ALERTE


def test_coherence_decomptes_ecart_massif_est_un_echec():
    scrutins, votes = _scrutins_et_votes(10, 8)
    assert quality.coherence_decomptes(scrutins, votes)["statut"] == ECHEC


def test_variable_constante_est_signalee():
    constante = pd.DataFrame({"dissident": [0] * 100})
    assert quality.equilibre_variable(constante, "dissident", "t")["statut"] == ALERTE
    variable = pd.DataFrame({"dissident": [0] * 95 + [1] * 5})
    assert quality.equilibre_variable(variable, "dissident", "t")["statut"] == OK


def test_plage_dates():
    df = pd.DataFrame({"d": ["2025-01-01", "2026-05-05"]})
    assert quality.plage_dates(df, "d", "t", "2024-07-01", "2029-12-31")["statut"] == OK
    assert quality.plage_dates(df, "d", "t", "2026-01-01", "2029-12-31")["statut"] == ALERTE


def test_echecs_filtre_le_rapport():
    rapport = pd.DataFrame({"statut": [OK, ECHEC, ALERTE]})
    assert len(quality.echecs(rapport)) == 1

"""Tests de la construction des variables d'analyse."""
from __future__ import annotations

import pandas as pd
import pytest

from lobbynomics import config
from lobbynomics.features import proximite_lobbies, scrutins_ensemble
from lobbynomics.models import diagnostic_separation, retirer_modalites_separantes


def test_scrutins_ensemble_ne_garde_que_les_votes_sur_le_texte():
    texte = config.TEXTES_PAR_CLE["agriculture"]
    scrutins = pd.DataFrame([
        {"dossier_ref": texte.dossier_ref, "date_scrutin": "2026-06-02",
         "titre": "l'ensemble du projet de loi d'urgence pour la protection…"},
        {"dossier_ref": texte.dossier_ref, "date_scrutin": "2026-05-20",
         "titre": "l'amendement n° 80 de Mme X à l'article 2 du projet de loi…"},
        {"dossier_ref": "AUTRE", "date_scrutin": "2026-06-02",
         "titre": "l'ensemble de la proposition de loi sur le sport"},
    ])
    resultat = scrutins_ensemble(scrutins, texte)
    assert len(resultat) == 1
    assert resultat.iloc[0]["date_scrutin"] == "2026-06-02"


def test_proximite_lobbies_repere_le_bon_lobby():
    """Deux députés, deux lobbies : chacun doit retrouver son homologue lexical."""
    amendements = pd.DataFrame([
        {"amendement_uid": "A1", "type_auteur": "Député", "acteur_ref": "PA1", "adopte": True,
         "expose": "Il faut sanctuariser la trajectoire budgétaire de la programmation "
                   "militaire et garantir les commandes d'armement terrestre. " * 4,
         "dispositif": ""},
        {"amendement_uid": "A2", "type_auteur": "Député", "acteur_ref": "PA2", "adopte": False,
         "expose": "Cet amendement protège les haies bocagères et encadre strictement "
                   "l'usage des produits phytosanitaires en zone de captage. " * 4,
         "dispositif": ""},
    ])
    ciblage = pd.DataFrame([
        {"cible_texte": True, "activite_id": "L1", "denomination": "INDUSTRIE DEFENSE",
         "objet": "Défendre la sanctuarisation de la trajectoire de la programmation "
                  "militaire et obtenir des commandes d'armement terrestre"},
        {"cible_texte": True, "activite_id": "L2", "denomination": "ASSOCIATION BOCAGE",
         "objet": "Protéger les haies bocagères et restreindre les produits "
                  "phytosanitaires dans les zones de captage"},
    ])
    resultat = proximite_lobbies(amendements, ciblage, min_caracteres=50).set_index("acteur_ref")
    assert resultat.loc["PA1", "lobby_le_plus_proche"] == "INDUSTRIE DEFENSE"
    assert resultat.loc["PA2", "lobby_le_plus_proche"] == "ASSOCIATION BOCAGE"
    assert (resultat["proximite_max"] > 0).all()


def test_proximite_vide_ne_plante_pas():
    vide = pd.DataFrame(columns=["amendement_uid", "type_auteur", "acteur_ref",
                                 "adopte", "expose", "dispositif"])
    ciblage = pd.DataFrame(columns=["cible_texte", "activite_id", "denomination", "objet"])
    assert proximite_lobbies(vide, ciblage).empty


def test_diagnostic_separation_detecte_les_modalites_constantes():
    donnees = pd.DataFrame({
        "vote_pour": [1, 1, 1, 0, 1, 0],
        "bloc": ["droite"] * 3 + ["gauche"] * 3,
    })
    table = diagnostic_separation(donnees, "vote_pour", "bloc")
    assert bool(table.loc["droite", "separe"]) is True
    assert bool(table.loc["gauche", "separe"]) is False


def test_retirer_modalites_separantes():
    donnees = pd.DataFrame({
        "converge": [1] * 20 + [0, 1] * 10,
        "bloc": ["droite"] * 20 + ["gauche"] * 20,
    })
    restant = retirer_modalites_separantes(donnees, "converge", "bloc", min_effectif=5)
    assert set(restant["bloc"]) == {"gauche"}


@pytest.mark.parametrize("cle", config.TEXTES_ANALYSE)
def test_chaque_texte_analyse_est_bien_configure(cle):
    texte = config.TEXTES_PAR_CLE[cle]
    assert texte.dossier_ref.startswith("DLR5L17")
    assert texte.alias, "un texte doit avoir au moins un alias pour être repérable"
    assert texte.mots_cles and texte.secteurs_hatvp

"""Tests des outils de robustesse."""
from __future__ import annotations

import pandas as pd

from lobbynomics import robustesse
from lobbynomics.features import (
    LEXIQUE_SECTEURS,
    classer_interets,
    dedoublonner_interets,
    profil_sectoriel_deputes,
)


def test_empreinte_est_stable_et_discriminante():
    a = pd.DataFrame({"x": [1, 2, 3], "y": ["a", "b", "c"]})
    assert robustesse._empreinte(a) == robustesse._empreinte(a.copy())
    # L'ordre des colonnes ne doit pas changer l'empreinte, la valeur si.
    assert robustesse._empreinte(a) == robustesse._empreinte(a[["y", "x"]])
    assert robustesse._empreinte(a) != robustesse._empreinte(a.assign(x=[1, 2, 4]))


def test_dedoublonnage_des_interets():
    """Une déclaration modificative recopie les intérêts inchangés."""
    interets = pd.DataFrame([
        {"nom_normalise": "jean dupont", "rubrique": "activProfCinqDerniere",
         "libelle_normalise": "banque x directeur"},
        {"nom_normalise": "jean dupont", "rubrique": "activProfCinqDerniere",
         "libelle_normalise": "banque x directeur"},
        {"nom_normalise": "jean dupont", "rubrique": "fonctionBenevole",
         "libelle_normalise": "club sportif"},
    ])
    assert len(dedoublonner_interets(interets)) == 2


def test_classement_sectoriel_multiple():
    interets = pd.DataFrame([
        {"libelle_normalise": "mutuelle sante du centre", "rubrique": "participationDirigeant"},
        {"libelle_normalise": "exploitation agricole familiale", "rubrique": "participationDirigeant"},
        {"libelle_normalise": "societe de conseil en strategie", "rubrique": "activConsultant"},
    ])
    classes = classer_interets(interets)
    assert set(classes.loc[0, "secteurs_interet"].split(" | ")) == {"FINANCE", "SANTE"}
    assert classes.loc[1, "secteurs_interet"] == "AGRI"
    assert classes.loc[2, "secteurs_interet"] == ""
    assert classes.loc[0, "n_secteurs"] == 2


def test_profil_exclut_les_mandats_electifs():
    """Presque tous les députés ont été élus locaux : la variable serait constante."""
    interets = pd.DataFrame([
        {"nom_normalise": "jean dupont", "rubrique": "mandatElectif",
         "libelle_normalise": "conseiller departemental", "secteurs_interet": "PUBLIC"},
        {"nom_normalise": "jean dupont", "rubrique": "participationDirigeant",
         "libelle_normalise": "exploitation agricole", "secteurs_interet": "AGRI"},
    ])
    deputes = pd.DataFrame([{"acteur_ref": "PA1", "nom_complet": "Jean Dupont",
                             "nom_normalise": "jean dupont", "groupe_abrev": "XX",
                             "bloc": "centre", "departement": "Ain", "commissions": ""}])
    profil = profil_sectoriel_deputes(interets, deputes)
    assert profil.loc[0, "AGRI"] == 1
    assert "PUBLIC" not in profil.columns   # le mandat électif n'est pas un intérêt privé


def test_lexique_sans_doublon_entre_secteurs():
    """Un même mot dans deux secteurs rendrait le classement ambigu et instable."""
    vus: dict[str, str] = {}
    collisions = []
    for secteur, mots in LEXIQUE_SECTEURS.items():
        for mot in mots:
            if mot in vus:
                collisions.append((mot, vus[mot], secteur))
            vus[mot] = secteur
    assert not collisions, f"mots partagés entre secteurs : {collisions}"


def test_concordance_renvoie_un_kappa():
    table = pd.DataFrame({
        "interet_sectoriel_declare": [True, True, False, False, False, False],
        "interet_secteur_lexique": [True, False, False, False, True, False],
    })
    croise = robustesse.concordance_mesures_interet(table)
    assert croise.to_numpy().sum() == 6
    assert 0 <= croise.attrs["accord"] <= 1
    assert croise.attrs["kappa"] <= 1

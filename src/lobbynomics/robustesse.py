"""Tests de robustesse : ce qui se passe quand on change les choix arbitraires.

Trois choix du projet n'ont aucune justification théorique et ont été faits à la
main : la largeur de la fenêtre temporelle autour du débat, la façon de résumer
la proximité lexicale d'un député, et la façon de repérer un intérêt sectoriel
déclaré. Un résultat qui dépend d'un de ces choix n'est pas un résultat.

Ce module rejoue les analyses en faisant varier chacun d'eux, et vérifie au
passage que deux exécutions identiques produisent exactement les mêmes nombres.
"""
from __future__ import annotations

import hashlib
import logging

import pandas as pd

from . import config, features, matching, models

logger = logging.getLogger(__name__)


def _empreinte(df: pd.DataFrame) -> str:
    """Empreinte stable d'une table, pour comparer deux exécutions."""
    return hashlib.sha256(
        pd.util.hash_pandas_object(df.sort_index(axis=1), index=False).values.tobytes()
    ).hexdigest()[:16]


# --------------------------------------------------------------------------
# 1. Largeur de la fenêtre temporelle
# --------------------------------------------------------------------------


def sensibilite_fenetre(*, activites: pd.DataFrame, dossiers: pd.DataFrame,
                        scrutins: pd.DataFrame, votes: pd.DataFrame,
                        deputes_hatvp: pd.DataFrame, amendements: pd.DataFrame,
                        departements: pd.DataFrame,
                        profil_sectoriel: pd.DataFrame | None = None,
                        marges: tuple[int, ...] = (0, 3, 6, 12, 24)) -> pd.DataFrame:
    """Rejoue la chaîne complète pour plusieurs largeurs de fenêtre.

    `config.MARGE_FENETRE_MOIS` vaut 6 par défaut, parce que le lobbying précède
    le dépôt d'un texte — mais six mois est un chiffre choisi, pas mesuré. On
    regarde donc ce que deviennent le volume d'activités retenues et le
    coefficient d'intérêt quand on va de 0 à 24 mois.
    """
    lignes = []
    marge_initiale = config.MARGE_FENETRE_MOIS
    try:
        for marge in marges:
            config.MARGE_FENETRE_MOIS = marge
            ciblage = matching.table_ciblage(activites, dossiers)
            table_finale = features.table_analyse(
                scrutins=scrutins, votes=votes, deputes_hatvp=deputes_hatvp,
                amendements=amendements, ciblage=ciblage, departements=departements,
                profil_sectoriel=profil_sectoriel)
            dissidence = features.table_dissidence(
                scrutins=scrutins, votes=votes, table_finale=table_finale)
            modele = models.modele_dissidence(dissidence)
            coefficients = modele["coefficients"]
            lignes.append({
                "marge_mois": marge,
                "activites_niveau_1": int(ciblage["cible_nommee"].sum()),
                "organisations": int(
                    ciblage.loc[ciblage["cible_nommee"], "identifiant_national"].nunique()),
                "n_votes": modele["n"],
                "coef_proximite": float(coefficients.loc["proximite_max_std", "coefficient"]),
                "p_proximite": float(coefficients.loc["proximite_max_std", "p_value"]),
                "pseudo_r2": modele["pseudo_r2"],
            })
            logger.info("fenêtre ±%2d mois → %4d activités de niveau 1, coef %.4f (p=%.3f)",
                        marge, lignes[-1]["activites_niveau_1"],
                        lignes[-1]["coef_proximite"], lignes[-1]["p_proximite"])
    finally:
        config.MARGE_FENETRE_MOIS = marge_initiale
    return pd.DataFrame(lignes)


# --------------------------------------------------------------------------
# 2. Façon de résumer la proximité
# --------------------------------------------------------------------------


def sensibilite_mesure_proximite(dissidence: pd.DataFrame) -> pd.DataFrame:
    """Compare `proximite_max` et `proximite_top5` comme variable d'exposition.

    Le maximum est sensible à un objet de lobbying isolé qui ressemblerait par
    hasard à un amendement ; la moyenne des cinq plus proches est plus stable
    mais dilue un ciblage très précis. Aucune des deux n'est « la bonne ».
    """
    lignes = []
    for mesure in ("proximite_max", "proximite_top5"):
        table = dissidence.copy()
        table["proximite_max"] = table[mesure]
        modele = models.modele_dissidence(table)
        coefficients = modele["coefficients"]
        lignes.append({
            "mesure": mesure,
            "n": modele["n"],
            "coefficient": float(coefficients.loc["proximite_max_std", "coefficient"]),
            "p_value": float(coefficients.loc["proximite_max_std", "p_value"]),
            "odds_ratio": float(coefficients.loc["proximite_max_std", "odds_ratio"]),
            "pseudo_r2": modele["pseudo_r2"],
        })
    return pd.DataFrame(lignes)


# --------------------------------------------------------------------------
# 3. Façon de repérer un intérêt sectoriel
# --------------------------------------------------------------------------


def sensibilite_mesure_interet(table_finale: pd.DataFrame) -> pd.DataFrame:
    """Compare les deux repérages de l'intérêt sectoriel déclaré.

    `interet_sectoriel_declare` cherche le vocabulaire du texte dans les libellés
    d'intérêts ; `interet_secteur_lexique` passe par un classement sectoriel
    explicite des employeurs et participations. Les deux sont bruités, et ne se
    recoupent que partiellement : c'est précisément pour ça qu'il faut publier
    les deux.
    """
    lignes = []
    for mesure in ("interet_sectoriel_declare", "interet_secteur_lexique"):
        if mesure not in table_finale.columns:
            continue
        table = table_finale.copy()
        table["interet_sectoriel_declare"] = table[mesure].astype(bool)
        modele = models.modele_specialisation(table)
        coefficients = modele["coefficients"]
        lignes.append({
            "mesure": mesure,
            "part_deputes_concernes": float(table[mesure].astype(bool).mean()),
            "n": modele["n"],
            "coefficient": float(coefficients.loc["interet_sectoriel_declare", "coefficient"]),
            "odds_ratio": float(coefficients.loc["interet_sectoriel_declare", "odds_ratio"]),
            "p_value": float(coefficients.loc["interet_sectoriel_declare", "p_value"]),
        })
    return pd.DataFrame(lignes)


def concordance_mesures_interet(table_finale: pd.DataFrame) -> pd.DataFrame:
    """Table de confusion entre les deux repérages, avec le kappa de Cohen.

    Deux mesures du même concept qui ne se recoupent qu'à la marge ne mesurent
    pas le même concept. Le dire avec un chiffre évite de choisir celle qui
    arrange.
    """
    if "interet_secteur_lexique" not in table_finale.columns:
        return pd.DataFrame()
    a = table_finale["interet_sectoriel_declare"].astype(bool)
    b = table_finale["interet_secteur_lexique"].astype(bool)
    croise = pd.crosstab(a, b, rownames=["repérage par vocabulaire du texte"],
                         colnames=["repérage par classement sectoriel"])
    accord = float((a == b).mean())
    hasard = float(a.mean() * b.mean() + (1 - a.mean()) * (1 - b.mean()))
    kappa = (accord - hasard) / (1 - hasard) if hasard < 1 else float("nan")
    croise.attrs["accord"] = accord
    croise.attrs["kappa"] = kappa
    logger.info("concordance des deux mesures d'intérêt : accord %.1f %%, kappa %.2f",
                100 * accord, kappa)
    return croise


# --------------------------------------------------------------------------
# 4. Déterminisme
# --------------------------------------------------------------------------


def verifier_determinisme(activites: pd.DataFrame, dossiers: pd.DataFrame,
                          amendements: pd.DataFrame, deputes_hatvp: pd.DataFrame,
                          ciblage: pd.DataFrame) -> pd.DataFrame:
    """Deux exécutions successives doivent produire exactement les mêmes nombres.

    Le projet contient deux sources d'aléa : le tirage de l'échantillon d'audit
    et le sous-échantillonnage du corpus placebo. Les deux sont à graine fixe —
    encore faut-il le vérifier, parce qu'une graine oubliée ne se voit jamais
    dans les résultats d'une seule exécution.
    """
    controles = []
    for nom, calcul in [
        ("table_ciblage", lambda: matching.table_ciblage(activites, dossiers)),
        ("echantillon_audit", lambda: matching.echantillon_audit(ciblage)),
        ("table_amendements",
         lambda: features.table_amendements(amendements, ciblage, deputes_hatvp)),
    ]:
        premiere, seconde = _empreinte(calcul()), _empreinte(calcul())
        controles.append({"calcul": nom, "empreinte_1": premiere, "empreinte_2": seconde,
                          "identique": premiere == seconde})
    rapport = pd.DataFrame(controles)
    if not rapport["identique"].all():
        logger.error("déterminisme rompu : %s",
                     rapport.loc[~rapport["identique"], "calcul"].tolist())
    else:
        logger.info("déterminisme vérifié sur %d calculs", len(rapport))
    return rapport

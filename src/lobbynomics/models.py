"""Étape 5 — modélisation.

Trois régressions logistiques, dans un ordre qui est un argument et pas un
catalogue :

1. ``modele_vote_final`` — le vote sur l'ensemble du texte expliqué par le seul
   bloc politique. Ce modèle est là pour **échouer utilement** : il sépare
   parfaitement les données. C'est le résultat qui justifie tout le reste.
2. ``modele_dissidence`` — sur les milliers de votes d'amendements, la
   probabilité qu'un député s'écarte de son groupe, expliquée par la proximité
   lexicale avec les demandes des lobbies, ses intérêts déclarés, la ruralité de
   sa circonscription et son appartenance de groupe.
3. ``modele_convergence`` — au niveau du député, la probabilité d'écrire des
   amendements lexicalement proches des demandes des lobbies du secteur.

Les écarts-types de (2) sont groupés par député : un même député apparaît dans
des centaines de scrutins, ses erreurs sont corrélées, et des écarts-types
classiques seraient artificiellement petits.
"""
from __future__ import annotations

import logging
import warnings

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

logger = logging.getLogger(__name__)


def _ajuster(formule: str, donnees: pd.DataFrame, *, groupes: pd.Series | None = None):
    """Ajuste un logit, avec écarts-types groupés si `groupes` est fourni."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # séparation parfaite = avertissement attendu
        modele = smf.logit(formule, data=donnees)
        if groupes is None:
            return modele.fit(disp=False, maxiter=200)
        return modele.fit(disp=False, maxiter=200, cov_type="cluster",
                          cov_kwds={"groups": groupes})


def resume(resultat, *, odds_ratio: bool = True) -> pd.DataFrame:
    """Tableau de coefficients lisible : effet, intervalle, p-value."""
    tableau = pd.DataFrame({
        "coefficient": resultat.params,
        "erreur_standard": resultat.bse,
        "z": resultat.tvalues,
        "p_value": resultat.pvalues,
    })
    ic = resultat.conf_int()
    tableau["ic_bas"], tableau["ic_haut"] = ic[0], ic[1]
    if odds_ratio:
        for colonne in ("coefficient", "ic_bas", "ic_haut"):
            tableau[f"or_{colonne}" if colonne != "coefficient" else "odds_ratio"] = \
                np.exp(tableau[colonne])
    tableau["significatif"] = tableau["p_value"] < 0.05
    return tableau.round(4)


def diagnostic_separation(donnees: pd.DataFrame, cible: str, facteur: str) -> pd.DataFrame:
    """Vérifie si un facteur sépare parfaitement la variable expliquée.

    Une modalité où la cible vaut toujours 0 ou toujours 1 rend le coefficient
    non identifiable : le maximum de vraisemblance part à l'infini. Mieux vaut le
    constater et le dire que publier des écarts-types de 10^8.
    """
    table = (donnees.dropna(subset=[cible, facteur])
             .groupby(facteur)[cible].agg(["mean", "size"])
             .rename(columns={"mean": "part_cible", "size": "effectif"}))
    table["separe"] = table["part_cible"].isin([0.0, 1.0])
    return table.round(4)



def retirer_modalites_separantes(donnees: pd.DataFrame, cible: str, facteur: str,
                                 *, min_effectif: int = 10) -> pd.DataFrame:
    """Écarte les modalités trop rares ou parfaitement séparantes d'un facteur.

    Sans ça, une modalité de dix observations toutes identiques envoie son
    coefficient à l'infini et contamine tout le tableau (p-values à NaN). On
    préfère dire franchement quelles modalités ont été écartées.
    """
    table = diagnostic_separation(donnees, cible, facteur)
    a_retirer = table.index[table["separe"] | (table["effectif"] < min_effectif)].tolist()
    if a_retirer:
        logger.info("modalités de %s écartées (séparantes ou < %d obs.) : %s",
                    facteur, min_effectif, ", ".join(map(str, a_retirer)))
    return donnees[~donnees[facteur].isin(a_retirer)].copy()


# --------------------------------------------------------------------------
# 1. Vote sur l'ensemble du texte
# --------------------------------------------------------------------------


def modele_vote_final(table: pd.DataFrame, texte_cle: str | None = None) -> dict:
    """Logit du vote « pour » sur l'ensemble du texte.

    Retourne un dictionnaire plutôt qu'un résultat statsmodels nu, parce que le
    diagnostic de séparation fait partie du résultat — et, ici, en constitue
    l'essentiel.
    """
    donnees = table[table["a_vote"]].copy()
    if texte_cle:
        donnees = donnees[donnees["texte_cle"] == texte_cle]
    donnees = donnees.dropna(subset=["vote_pour", "bloc"])

    separation = diagnostic_separation(donnees, "vote_pour", "bloc")
    effectif_separe = int(separation.loc[separation["separe"], "effectif"].sum())
    part_separee = effectif_separe / len(donnees) if len(donnees) else float("nan")

    sortie: dict = {
        "n": len(donnees),
        "part_pour": float(donnees["vote_pour"].mean()),
        "separation": separation,
        "part_observations_separees": part_separee,
        "separation_parfaite": bool(separation["separe"].all()),
    }

    formule = "vote_pour ~ C(bloc) + proximite_max + interet_sectoriel_declare + part_rurale"
    sortie["formule"] = formule
    if part_separee > 0.9:
        logger.warning(
            "vote final%s : le bloc politique sépare %.1f %% des observations "
            "(%d des %d modalités à 0 %% ou 100 %%) — le maximum de vraisemblance "
            "n'est pas identifiable. C'est le résultat, pas un bug.",
            f" [{texte_cle}]" if texte_cle else "", 100 * part_separee,
            int(separation["separe"].sum()), len(separation))
        sortie["identifiable"] = False
        return sortie

    try:
        resultat = _ajuster(formule, donnees)
    except (np.linalg.LinAlgError, Exception) as err:  # séparation quasi complète
        logger.warning("vote final%s : ajustement impossible (%s) — séparation quasi complète",
                       f" [{texte_cle}]" if texte_cle else "", type(err).__name__)
        sortie["identifiable"] = False
        sortie["erreur_ajustement"] = f"{type(err).__name__}: {err}"
        return sortie

    sortie.update({"identifiable": True, "resultat": resultat,
                   "coefficients": resume(resultat),
                   "pseudo_r2": float(resultat.prsquared)})
    return sortie


def pouvoir_predictif_bloc(table: pd.DataFrame) -> pd.DataFrame:
    """Part des votes correctement prédits par la seule règle « vote du bloc ».

    Alternative honnête au logit non identifiable : on prédit pour chaque député
    le vote majoritaire de son bloc sur le texte, et on compte les erreurs.
    """
    donnees = table[table["a_vote"]].dropna(subset=["vote_pour", "bloc"]).copy()
    majorite = (donnees.groupby(["texte_cle", "bloc"])["vote_pour"]
                .transform(lambda s: int(s.mean() >= 0.5)))
    donnees["prediction_bloc"] = majorite
    donnees["correct"] = donnees["prediction_bloc"] == donnees["vote_pour"]
    return (donnees.groupby("texte_cle")
            .agg(n=("correct", "size"), part_pour=("vote_pour", "mean"),
                 exactitude_regle_bloc=("correct", "mean"),
                 nb_votes_atypiques=("correct", lambda s: int((~s).sum())))
            .round(4))


# --------------------------------------------------------------------------
# 2. Dissidence sur les votes d'amendements
# --------------------------------------------------------------------------

FORMULE_DISSIDENCE = (
    "dissident ~ proximite_max_std + interet_sectoriel_declare + part_rurale_std"
    " + dans_commission_competente + a_depose_amendement + C(bloc) + C(texte_cle)"
)


def preparer_dissidence(table: pd.DataFrame) -> pd.DataFrame:
    """Centre et réduit les variables continues, pour des coefficients comparables."""
    donnees = table.dropna(subset=["dissident", "bloc", "part_rurale"]).copy()
    for colonne in ("proximite_max", "part_rurale"):
        serie = donnees[colonne].astype(float)
        donnees[f"{colonne}_std"] = (serie - serie.mean()) / serie.std(ddof=0)
    donnees["interet_sectoriel_declare"] = donnees["interet_sectoriel_declare"].astype(int)
    donnees["dans_commission_competente"] = donnees["dans_commission_competente"].astype(int)
    donnees["a_depose_amendement"] = donnees["a_depose_amendement"].astype(int)
    return donnees


def modele_dissidence(table: pd.DataFrame, *, formule: str = FORMULE_DISSIDENCE,
                      texte_cle: str | None = None) -> dict:
    """Logit de la dissidence, écarts-types groupés par député."""
    donnees = preparer_dissidence(table)
    if texte_cle:
        donnees = donnees[donnees["texte_cle"] == texte_cle]
        formule = formule.replace(" + C(texte_cle)", "")
    resultat = _ajuster(formule, donnees, groupes=donnees["acteur_ref"])
    logger.info("modèle de dissidence%s : n=%d, pseudo-R²=%.4f, %d députés",
                f" [{texte_cle}]" if texte_cle else "", len(donnees),
                resultat.prsquared, donnees["acteur_ref"].nunique())
    return {
        "n": len(donnees),
        "n_deputes": int(donnees["acteur_ref"].nunique()),
        "taux_dissidence": float(donnees["dissident"].mean()),
        "formule": formule,
        "resultat": resultat,
        "coefficients": resume(resultat),
        "pseudo_r2": float(resultat.prsquared),
    }


def effets_marginaux(resultat) -> pd.DataFrame:
    """Effets marginaux moyens : en points de pourcentage, directement lisibles."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        marges = resultat.get_margeff(at="overall")
    tableau = marges.summary_frame()
    tableau.columns = ["effet_marginal", "erreur_standard", "z", "p_value", "ic_bas", "ic_haut"]
    tableau["effet_points_pct"] = 100 * tableau["effet_marginal"]
    return tableau.round(4)


# --------------------------------------------------------------------------
# 3. Convergence lexicale avec les demandes des lobbies
# --------------------------------------------------------------------------


def modele_convergence(table: pd.DataFrame) -> dict:
    """Qui écrit des amendements proches des demandes déclarées des lobbies ?

    Variable expliquée : le député est-il au-dessus de la médiane de proximité
    lexicale, parmi les seuls députés qui ont déposé au moins un amendement sur
    le texte (sinon la variable n'est pas définie et le 0 n'a pas de sens).
    """
    donnees = table[table["a_depose_amendement"] & table["proximite_max"].gt(0)].copy()
    donnees = donnees.dropna(subset=["part_rurale", "bloc"])
    mediane = donnees.groupby("texte_cle")["proximite_max"].transform("median")
    donnees["converge"] = (donnees["proximite_max"] > mediane).astype(int)
    donnees["part_rurale_std"] = (
        (donnees["part_rurale"] - donnees["part_rurale"].mean()) / donnees["part_rurale"].std(ddof=0))
    donnees["interet_sectoriel_declare"] = donnees["interet_sectoriel_declare"].astype(int)
    donnees["dans_commission_competente"] = donnees["dans_commission_competente"].astype(int)
    donnees["log_amendements"] = np.log1p(donnees["nb_amendements_texte"])
    donnees = retirer_modalites_separantes(donnees, "converge", "bloc", min_effectif=15)

    formule = ("converge ~ part_rurale_std + interet_sectoriel_declare"
               " + dans_commission_competente + log_amendements + C(bloc)")
    resultat = _ajuster(formule, donnees, groupes=donnees["acteur_ref"])
    logger.info("modèle de convergence : n=%d députés-textes, pseudo-R²=%.4f",
                len(donnees), resultat.prsquared)
    return {"n": len(donnees), "formule": formule, "resultat": resultat,
            "coefficients": resume(resultat), "pseudo_r2": float(resultat.prsquared)}

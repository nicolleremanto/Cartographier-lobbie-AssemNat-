"""Orchestration : de l'URL brute aux tables d'analyse et aux figures.

Un seul point d'entrée, `executer`, pour que « relancer le projet » soit une
commande et pas un rituel. Chaque étape écrit son résultat dans
`data/processed/`, et l'étape suivante le relit : le pipeline est donc
reprenable, et le notebook de rapport ne fait que lire ces tables.

    python -m lobbynomics.pipeline              # tout
    python -m lobbynomics.pipeline --etapes matching features modeles
    python -m lobbynomics.pipeline --force      # retélécharge les sources
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from typing import Any

import pandas as pd

from . import collect, config, features, matching, models, parse_an, parse_hatvp, viz

logger = logging.getLogger(__name__)

ETAPES = ("collecte", "parsing", "matching", "features", "modeles", "figures")


def lire(nom: str) -> pd.DataFrame:
    chemin = config.PROCESSED / f"{nom}.parquet"
    if not chemin.exists():
        raise FileNotFoundError(
            f"table manquante : {chemin.name}. Lancez les étapes précédentes "
            f"(python -m lobbynomics.pipeline).")
    return pd.read_parquet(chemin)


def ecrire(df: pd.DataFrame, nom: str) -> None:
    chemin = config.PROCESSED / f"{nom}.parquet"
    df.to_parquet(chemin, index=False)
    logger.info("→ %s (%d lignes, %.1f Mo)", chemin.name, len(df),
                chemin.stat().st_size / 1e6)


# --------------------------------------------------------------------------
# Étapes
# --------------------------------------------------------------------------


def etape_collecte(*, force: bool = False) -> None:
    collect.tout_recuperer(force=force)


def etape_parsing() -> None:
    parse_an.construire_tables_an()
    parse_hatvp.construire_tables_hatvp()


def etape_matching() -> None:
    scrutins = matching.rattacher_scrutins(lire("an_scrutins"), lire("an_dossiers"))
    ecrire(scrutins, "scrutins_rattaches")
    ecrire(matching.evaluer_rattachement(scrutins), "audit_rattachement_scrutins")

    ciblage = matching.table_ciblage(lire("hatvp_activites"), lire("an_dossiers"))
    ecrire(ciblage, "ciblage_hatvp")

    audit = matching.echantillon_audit(ciblage)
    chemin_audit = config.PROCESSED / "audit_ciblage_a_annoter.csv"
    if chemin_audit.exists():
        logger.info("échantillon d'audit déjà présent, conservé (il contient des "
                    "annotations manuelles) : %s", chemin_audit.name)
    else:
        audit.to_csv(chemin_audit, index=False)
        logger.info("→ %s : à annoter à la main (colonne verdict_manuel : oui/non)",
                    chemin_audit.name)

    deputes = matching.rattacher_deputes_hatvp(
        lire("an_deputes"), lire("hatvp_index_declarations"), lire("hatvp_interets_deputes"))
    ecrire(deputes, "deputes_hatvp")


def etape_features() -> None:
    scrutins = lire("scrutins_rattaches")
    amendements = lire("an_amendements").merge(
        lire("an_textes_dossiers"), on="texte_ref", how="left")
    ciblage = lire("ciblage_hatvp")

    table_finale = features.table_analyse(
        scrutins=scrutins, votes=lire("an_votes"), deputes_hatvp=lire("deputes_hatvp"),
        amendements=amendements, ciblage=ciblage, departements=lire("geo_departements"))
    ecrire(table_finale, "analyse_votes_finaux")

    ecrire(features.table_dissidence(scrutins=scrutins, votes=lire("an_votes"),
                                     table_finale=table_finale),
           "analyse_dissidence")

    # Robustesse : le même tableau construit sur la deuxième lecture.
    try:
        ecrire(features.table_analyse(
            scrutins=scrutins, votes=lire("an_votes"),
            deputes_hatvp=lire("deputes_hatvp"), amendements=amendements,
            ciblage=ciblage, departements=lire("geo_departements"), rang_scrutin=1),
            "analyse_votes_finaux_lecture2")
    except (IndexError, KeyError, ValueError) as err:
        logger.warning("table de robustesse (2e lecture) non produite : %s", err)

    aretes = []
    for cle in config.TEXTES_ANALYSE:
        texte = config.TEXTES_PAR_CLE[cle]
        morceau = features.aretes_biparties(
            amendements[amendements["dossier_ref"] == texte.dossier_ref],
            ciblage[ciblage["texte_cle"] == cle])
        morceau["texte_cle"] = cle
        aretes.append(morceau)
    ecrire(pd.concat(aretes, ignore_index=True), "graphe_aretes")


def etape_modeles() -> dict[str, Any]:
    table_finale, dissidence = lire("analyse_votes_finaux"), lire("analyse_dissidence")

    resultats: dict[str, Any] = {}
    vote = models.modele_vote_final(table_finale)
    resultats["vote_final"] = {
        "n": vote["n"], "part_pour": vote["part_pour"],
        "part_observations_separees": vote["part_observations_separees"],
        "identifiable": vote.get("identifiable", False),
    }
    predictif = models.pouvoir_predictif_bloc(table_finale)
    predictif.to_csv(config.PROCESSED / "pouvoir_predictif_bloc.csv")
    resultats["regle_bloc"] = predictif.to_dict("index")

    dis = models.modele_dissidence(dissidence)
    dis["coefficients"].to_csv(config.PROCESSED / "coefficients_dissidence.csv")
    models.effets_marginaux(dis["resultat"]).to_csv(
        config.PROCESSED / "effets_marginaux_dissidence.csv")
    resultats["dissidence"] = {"n": dis["n"], "n_deputes": dis["n_deputes"],
                               "taux_dissidence": dis["taux_dissidence"],
                               "pseudo_r2": dis["pseudo_r2"]}

    conv = models.modele_convergence(table_finale)
    conv["coefficients"].to_csv(config.PROCESSED / "coefficients_convergence.csv")
    resultats["convergence"] = {"n": conv["n"], "pseudo_r2": conv["pseudo_r2"]}

    (config.REPORTS / "resultats_modeles.json").write_text(
        json.dumps(resultats, ensure_ascii=False, indent=2, default=str), "utf-8")
    return resultats


def etape_figures() -> list[str]:
    viz.style()
    ciblage, table_finale = lire("ciblage_hatvp"), lire("analyse_votes_finaux")
    dissidence, aretes = lire("analyse_dissidence"), lire("graphe_aretes")
    deputes = lire("deputes_hatvp")

    chemins = [
        viz.enregistrer(viz.figure_qualite_matching(lire("audit_rattachement_scrutins")),
                        "01_qualite_matching"),
        viz.enregistrer(viz.figure_intensite_lobbying(ciblage), "02_intensite_lobbying"),
        viz.enregistrer(viz.figure_secteurs_textes(ciblage), "03_secteurs_par_texte"),
        viz.enregistrer(viz.figure_votes_par_bloc(table_finale), "04_votes_par_bloc"),
        viz.enregistrer(viz.figure_dissidence(dissidence), "05_dissidence_par_bloc"),
        viz.enregistrer(viz.figure_proximite(table_finale), "06_proximite_lexicale"),
    ]
    for cle in config.TEXTES_ANALYSE:
        chemins.append(viz.enregistrer(viz.figure_top_organisations(ciblage, cle),
                                       f"07_top_organisations_{cle}"))
        figure, _ = viz.figure_graphe_biparti(
            aretes[aretes["texte_cle"] == cle], deputes, titre_texte=cle)
        chemins.append(viz.enregistrer(figure, f"08_graphe_{cle}"))

    coefficients = pd.read_csv(config.PROCESSED / "coefficients_dissidence.csv", index_col=0)
    chemins.append(viz.enregistrer(
        viz.figure_coefficients(coefficients,
                                titre="Ce qui prédit un vote dissident sur un amendement"),
        "09_coefficients_dissidence"))
    return chemins


# --------------------------------------------------------------------------
# Point d'entrée
# --------------------------------------------------------------------------


def executer(etapes: tuple[str, ...] = ETAPES, *, force: bool = False) -> None:
    for etape in etapes:
        if etape not in ETAPES:
            raise ValueError(f"étape inconnue : {etape} (connues : {ETAPES})")
        debut = time.perf_counter()
        logger.info("══ étape %s ══", etape)
        if etape == "collecte":
            etape_collecte(force=force)
        elif etape == "parsing":
            etape_parsing()
        elif etape == "matching":
            etape_matching()
        elif etape == "features":
            etape_features()
        elif etape == "modeles":
            etape_modeles()
        elif etape == "figures":
            etape_figures()
        logger.info("══ %s terminé en %.1f s ══", etape, time.perf_counter() - debut)


def main() -> None:  # pragma: no cover
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--etapes", nargs="+", default=list(ETAPES),
                           choices=list(ETAPES), help="étapes à exécuter")
    analyseur.add_argument("--force", action="store_true",
                           help="retélécharge et redécompresse les sources")
    analyseur.add_argument("--silencieux", action="store_true")
    args = analyseur.parse_args()
    logging.basicConfig(level=logging.WARNING if args.silencieux else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
                        datefmt="%H:%M:%S")
    executer(tuple(args.etapes), force=args.force)


if __name__ == "__main__":  # pragma: no cover
    main()

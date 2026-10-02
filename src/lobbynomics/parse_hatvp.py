"""Étape 2b — mise à plat des données HATVP.

Deux familles de fichiers, deux rôles distincts dans le projet :

1. **Le répertoire des représentants d'intérêts** (`agora_repertoire_opendata.json`)
   dit *qui déclare faire du lobbying sur quoi*. Sa granularité est l'« activité » :
   un objet en texte libre (« limiter le champ de la décision de la Cour de
   cassation sur les congés payés… »), des domaines d'intervention, et une liste
   d'actions précisant le type de décideur public visé et le type de décision.
   C'est de là que viendra la variable d'exposition au lobbying.

2. **Les déclarations des responsables publics** (`liste.csv` + `declarations.xml`)
   disent *ce que les députés eux-mêmes déclarent* : anciens employeurs,
   participations, fonctions bénévoles. C'est la matière du volet « pantouflage »
   et, surtout, une variable de contrôle individuelle.

Point méthodologique important, répété dans le rapport : une activité n'est datée
qu'à l'exercice (l'année civile). Il n'y a **aucun** numéro de texte de loi dans
le répertoire. Tout rapprochement avec l'Assemblée est donc une inférence, et
c'est le module `matching` qui en assume le coût.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from datetime import date, datetime

import pandas as pd
from lxml import etree

from . import config
from .parse_an import normaliser

logger = logging.getLogger(__name__)

NON_PUBLIE = re.compile(r"\[\s*Donn[ée]es non publi[ée]es\s*\]", re.IGNORECASE)


# --------------------------------------------------------------------------
# 1. Répertoire des représentants d'intérêts
# --------------------------------------------------------------------------


def _date_fr(valeur: str | None) -> date | None:
    """Lit les deux formats de date du répertoire : ``JJ-MM-AAAA`` et ``JJ/MM/AAAA``."""
    if not valeur:
        return None
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(valeur.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _organisations(publications: list[dict]) -> pd.DataFrame:
    """Une organisation inscrite au répertoire par ligne."""
    lignes = []
    for org in publications:
        cat = org.get("categorieOrganisation") or {}
        act = org.get("activites") or {}
        lignes.append({
            "identifiant_national": org.get("identifiantNational"),
            "denomination": org.get("denomination"),
            "categorie_code": cat.get("code"),
            "categorie_label": cat.get("label"),
            "categorie_famille": cat.get("categorie"),
            "ville": org.get("ville"),
            "code_postal": org.get("codePostal"),
            "pays": org.get("pays"),
            "site_web": org.get("lienSiteWeb"),
            "nb_dirigeants": len(org.get("dirigeants") or []),
            "nb_collaborateurs": len(org.get("collaborateurs") or []),
            "nb_clients": len(org.get("clients") or []),
            "declaration_tiers": bool(org.get("declarationTiers")),
            "secteurs": " | ".join(
                s.get("code", "") for s in act.get("listSecteursActivites") or []),
            "secteurs_label": " | ".join(
                s.get("label", "") for s in act.get("listSecteursActivites") or []),
            "niveaux_intervention": " | ".join(
                n.get("code", "") for n in act.get("listNiveauIntervention") or []),
            "date_premiere_publication": _date_fr(org.get("datePremierePublication")),
        })
    df = pd.DataFrame(lignes).drop_duplicates("identifiant_national")
    df["denomination_normalisee"] = df["denomination"].map(normaliser)
    logger.info("organisations HATVP : %d lignes, %d catégories",
                len(df), df["categorie_famille"].nunique())
    return df


def _activites(publications: list[dict]) -> pd.DataFrame:
    """Une activité de représentation d'intérêts déclarée par ligne."""
    lignes = []
    for org in publications:
        id_org = org.get("identifiantNational")
        denom = org.get("denomination")
        cat = (org.get("categorieOrganisation") or {})
        secteurs = " | ".join(
            s.get("code", "")
            for s in ((org.get("activites") or {}).get("listSecteursActivites") or []))

        for exercice in org.get("exercices") or []:
            ex = exercice.get("publicationCourante") or {}
            debut, fin = _date_fr(ex.get("dateDebut")), _date_fr(ex.get("dateFin"))
            for activite in ex.get("activites") or []:
                a = activite.get("publicationCourante") or {}
                actions = a.get("actionsRepresentationInteret") or []
                # Les actions précisent qui est visé et quel type de décision :
                # on les agrège en ensembles, une activité pouvant en porter plusieurs.
                responsables, decisions, menees, tiers = set(), set(), set(), set()
                observations = []
                for ar in actions:
                    responsables.update(ar.get("reponsablesPublics") or [])  # faute d'orthographe dans la source
                    decisions.update(ar.get("decisionsConcernees") or [])
                    menees.update(ar.get("actionsMenees") or [])
                    tiers.update(ar.get("tiers") or [])
                    if ar.get("observation"):
                        observations.append(ar["observation"])

                lignes.append({
                    "activite_id": a.get("identifiantFiche"),
                    "identifiant_national": id_org,
                    "denomination": denom,
                    "categorie_famille": cat.get("categorie"),
                    "secteurs": secteurs,
                    "exercice_id": ex.get("exerciceId"),
                    "exercice_debut": debut,
                    "exercice_fin": fin,
                    "exercice_annee": debut.year if debut else None,
                    "objet": a.get("objet"),
                    "domaines": " | ".join(a.get("domainesIntervention") or []),
                    "nb_actions": len(actions),
                    "responsables_publics": " | ".join(sorted(responsables)),
                    "decisions_concernees": " | ".join(sorted(decisions)),
                    "actions_menees": " | ".join(sorted(menees)),
                    "tiers": " | ".join(sorted(tiers)),
                    "observation": " ; ".join(observations) or None,
                    "montant_depense": ex.get("montantDepense"),
                    "nb_salaries": ex.get("nombreSalaries"),
                })

    df = pd.DataFrame(lignes)
    df["objet_normalise"] = df["objet"].map(normaliser)
    # Deux indicateurs très utilisés par la suite.
    df["cible_parlement"] = df["responsables_publics"].str.contains(
        "Député|sénateur|parlementaire", case=False, na=False)
    df["cible_loi"] = df["decisions_concernees"].str.contains("Lois", case=False, na=False)
    logger.info(
        "activités HATVP : %d lignes (%d visant le Parlement, %d portant sur une loi), "
        "%d organisations déclarantes",
        len(df), int(df["cible_parlement"].sum()), int(df["cible_loi"].sum()),
        df["identifiant_national"].nunique())
    return df


def charger_repertoire() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retourne ``(organisations, activites)`` depuis le répertoire HATVP."""
    chemin = config.RAW / config.SOURCES["hatvp_repertoire"]["filename"]
    with chemin.open(encoding="utf-8") as fh:
        publications = json.load(fh)["publications"]
    logger.info("répertoire HATVP : %d fiches d'organisation lues", len(publications))
    return _organisations(publications), _activites(publications)


# --------------------------------------------------------------------------
# 2. Index des déclarations des responsables publics (liste.csv)
# --------------------------------------------------------------------------


def charger_index_declarations() -> pd.DataFrame:
    """Index des déclarations HATVP, restreint aux députés.

    La colonne ``url_dossier`` est la clé de jointure propre avec l'Assemblée :
    le champ ``uri_hatvp`` de chaque acteur pointe exactement sur cette page.
    """
    chemin = config.RAW / config.SOURCES["hatvp_liste"]["filename"]
    df = pd.read_csv(chemin, sep=";", dtype=str, low_memory=False)
    df.columns = [c.strip() for c in df.columns]
    deputes = df[df["type_mandat"].eq("depute")].copy()
    deputes["uri_hatvp"] = "https://www.hatvp.fr" + deputes["url_dossier"].str.strip()
    deputes["date_depot"] = pd.to_datetime(deputes["date_depot"], errors="coerce")
    deputes["date_publication"] = pd.to_datetime(deputes["date_publication"], errors="coerce")
    deputes["nom_normalise"] = (
        deputes["prenom"].fillna("") + " " + deputes["nom"].fillna("")).map(normaliser)
    logger.info("index déclarations : %d lignes députés, %d personnes, types %s",
                len(deputes), deputes["uri_hatvp"].nunique(),
                sorted(deputes["type_document"].dropna().unique()))
    return deputes


# --------------------------------------------------------------------------
# 3. Contenu des déclarations d'intérêts (declarations.xml)
# --------------------------------------------------------------------------

#: Rubriques de la déclaration d'intérêts retenues, et champs porteurs du nom
#: de l'organisation concernée.
RUBRIQUES: dict[str, tuple[str, ...]] = {
    "activProfCinqDerniereDto": ("employeur", "description"),
    "activProfConjointDto": ("employeur", "description"),
    "activConsultantDto": ("nomSociete", "descriptionActivite", "description"),
    "participationDirigeantDto": ("nomSociete", "descriptionActivite", "description"),
    "participationFinanciereDto": ("nomSociete", "description"),
    "fonctionBenevoleDto": ("nomStructure", "descriptionActivite"),
    "mandatElectifDto": ("descriptionMandat",),
}


def _texte(noeud) -> str:
    """Texte d'un nœud XML, purgé du marqueur « Données non publiées »."""
    if noeud is None or noeud.text is None:
        return ""
    return NON_PUBLIE.sub("", noeud.text).strip()


def _items(declaration, rubrique: str) -> Iterator[dict]:
    """Itère sur les ``items/items`` d'une rubrique de déclaration."""
    bloc = declaration.find(rubrique)
    if bloc is None or bloc.findtext("neant") == "true":
        return
    conteneur = bloc.find("items")
    if conteneur is None:
        return
    for item in conteneur.findall("items"):
        yield item


def charger_interets_deputes() -> pd.DataFrame:
    """Une ligne par intérêt déclaré par un député (rubrique × organisation).

    Le fichier pèse 80 Mo : on le lit en `iterparse` et on libère chaque nœud,
    pour que l'empreinte mémoire reste constante.
    """
    chemin = config.RAW / config.SOURCES["hatvp_declarations"]["filename"]
    lignes = []
    nb_declarations = 0

    for _, decl in etree.iterparse(str(chemin), events=("end",), tag="declaration"):
        general = decl.find("general")
        if general is None:
            decl.clear()
            continue
        if general.findtext("qualiteMandat/codCategorieMandat") != "PAR" or \
                general.findtext("qualiteMandat/labelTypeMandat") != "Député":
            decl.clear()
            continue

        nb_declarations += 1
        declarant = general.find("declarant")
        base = {
            "declaration_uuid": decl.findtext("uuid"),
            "type_declaration": general.findtext("typeDeclaration/id"),
            "type_declaration_label": general.findtext("typeDeclaration/label"),
            "date_depot": _date_fr(decl.findtext("dateDepot")),
            "nom": _texte(declarant.find("nom")) if declarant is not None else "",
            "prenom": _texte(declarant.find("prenom")) if declarant is not None else "",
            "date_naissance": _date_fr(
                _texte(declarant.find("dateNaissance")) if declarant is not None else None),
        }

        for rubrique, champs in RUBRIQUES.items():
            for item in _items(decl, rubrique):
                morceaux = [_texte(item.find(c)) for c in champs]
                libelle = " — ".join(m for m in morceaux if m)
                if not libelle:
                    continue
                lignes.append({
                    **base,
                    "rubrique": rubrique.replace("Dto", ""),
                    "libelle": libelle,
                    "organisation": next((m for m in morceaux if m), ""),
                    "date_debut": _texte(item.find("dateDebut")) or None,
                    "date_fin": _texte(item.find("dateFin")) or None,
                    "conservee": item.findtext("conservee"),
                })
        decl.clear()
        while decl.getprevious() is not None:
            del decl.getparent()[0]

    df = pd.DataFrame(lignes)
    if not df.empty:
        df["nom_normalise"] = (df["prenom"] + " " + df["nom"]).map(normaliser)
        df["libelle_normalise"] = df["libelle"].map(normaliser)
    logger.info("intérêts déclarés : %d lignes issues de %d déclarations de députés",
                len(df), nb_declarations)
    return df


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def construire_tables_hatvp(*, ecrire: bool = True) -> dict[str, pd.DataFrame]:
    organisations, activites = charger_repertoire()
    tables = {
        "hatvp_organisations": organisations,
        "hatvp_activites": activites,
        "hatvp_index_declarations": charger_index_declarations(),
        "hatvp_interets_deputes": charger_interets_deputes(),
        "geo_departements": charger_departements(),
    }
    if ecrire:
        for nom, df in tables.items():
            chemin = config.PROCESSED / f"{nom}.parquet"
            df.to_parquet(chemin, index=False)
            logger.info("écrit %s (%d lignes, %.1f Mo)",
                        chemin.name, len(df), chemin.stat().st_size / 1e6)
    return tables


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    construire_tables_hatvp()


# --------------------------------------------------------------------------
# 4. Contexte territorial (API Géo) — variable de contrôle rural/urbain
# --------------------------------------------------------------------------


def charger_departements() -> pd.DataFrame:
    """Un département par ligne : population, superficie, densité, part rurale.

    La « part rurale » est la fraction de la population du département vivant
    dans une commune de moins de 2 000 habitants. C'est un indicateur plus
    parlant que la densité brute, qui est tirée vers le haut par une seule
    grande ville (le Rhône et la Lozère ont des densités incomparables, mais la
    question pertinente pour un vote agricole est « combien d'électeurs vivent
    en petite commune »).
    """
    chemin = config.RAW / config.SOURCES["geo_communes"]["filename"]
    with chemin.open(encoding="utf-8") as fh:
        communes = json.load(fh)

    df = pd.json_normalize(communes)
    df = df.rename(columns={"departement.code": "num_departement",
                            "departement.nom": "departement"})
    df["population"] = pd.to_numeric(df["population"], errors="coerce").fillna(0)
    # L'API Géo exprime les surfaces en hectares.
    df["surface_km2"] = pd.to_numeric(df["surface"], errors="coerce") / 100
    df["petite_commune"] = df["population"] < 2000

    agr = df.groupby(["num_departement", "departement"], as_index=False).agg(
        population=("population", "sum"),
        surface_km2=("surface_km2", "sum"),
        nb_communes=("code", "size"),
        population_petites_communes=("population", lambda s: s[df.loc[s.index, "petite_commune"]].sum()),
    )
    agr["densite_hab_km2"] = agr["population"] / agr["surface_km2"]
    agr["part_rurale"] = agr["population_petites_communes"] / agr["population"].replace(0, pd.NA)
    agr["departement_normalise"] = agr["departement"].map(normaliser)
    logger.info("départements : %d lignes, part rurale médiane %.2f",
                len(agr), agr["part_rurale"].median())
    return agr

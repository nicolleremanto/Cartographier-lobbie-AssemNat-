"""Étape 2a — mise à plat de l'open data de l'Assemblée nationale.

Les fichiers de l'Assemblée sont du XML converti en JSON : très imbriqués, avec
des conventions pénibles (un champ est soit absent, soit un dict ``{"@xsi:nil":
"true"}``, soit une chaîne ; une liste à un élément devient un dict). Tout le
sale travail est confiné ici, et quatre tables plates en sortent :

``deputes``      un député par ligne (identité, groupe, circonscription, commission)
``dossiers``     un dossier législatif par ligne (titre, fenêtre de débat, textes associés)
``votes``        un vote nominatif par ligne (député × scrutin)
``amendements``  un amendement par ligne (auteur, texte visé, article, sort)
"""
from __future__ import annotations

import html
import json
import logging
import re
import unicodedata
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd

from . import config

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Utilitaires de lecture du JSON « à la mode Assemblée »
# --------------------------------------------------------------------------


def _txt(valeur: Any) -> str | None:
    """Ramène un champ Assemblée à une chaîne, ou None.

    Gère les trois formes rencontrées : chaîne nue, ``{"#text": "..."}`` et le
    marqueur de nullité XML ``{"@xsi:nil": "true"}``.
    """
    if valeur is None:
        return None
    if isinstance(valeur, str):
        valeur = valeur.strip()
        return valeur or None
    if isinstance(valeur, dict):
        if valeur.get("@xsi:nil") == "true":
            return None
        if "#text" in valeur:
            return _txt(valeur["#text"])
    return None


def _liste(valeur: Any) -> list:
    """Force un champ « 0, 1 ou n » en liste Python."""
    if valeur is None:
        return []
    if isinstance(valeur, list):
        return valeur
    if isinstance(valeur, dict) and valeur.get("@xsi:nil") == "true":
        return []
    return [valeur]


def _charger(dossier: Path, racine: str) -> Iterator[dict]:
    """Itère sur les objets ``racine`` de tous les JSON d'une arborescence."""
    for chemin in sorted(dossier.rglob("*.json")):
        try:
            with chemin.open(encoding="utf-8") as fh:
                contenu = json.load(fh)
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            logger.warning("fichier illisible ignoré : %s (%s)", chemin.name, err)
            continue
        objet = contenu.get(racine)
        if objet:
            yield objet


_BALISES = re.compile(r"<[^>]+>")
_ESPACES = re.compile(r"\s+")


def nettoyer_html(brut: str | None) -> str:
    """Transforme un fragment HTML de l'Assemblée en texte brut lisible."""
    if not brut:
        return ""
    texte = html.unescape(html.unescape(brut))      # double échappement fréquent
    texte = _BALISES.sub(" ", texte)
    texte = texte.replace("\xa0", " ").replace("‑", "-").replace("’", "'")
    return _ESPACES.sub(" ", texte).strip()


def normaliser(texte: str | None) -> str:
    """Minuscules, sans accents, sans ponctuation : la forme utilisée pour comparer."""
    if not texte:
        return ""
    texte = unicodedata.normalize("NFKD", texte)
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    texte = texte.lower().replace("’", " ").replace("'", " ")
    texte = re.sub(r"[^a-z0-9 ]+", " ", texte)
    return _ESPACES.sub(" ", texte).strip()


# --------------------------------------------------------------------------
# Députés (acteurs + mandats + organes)
# --------------------------------------------------------------------------


def charger_organes() -> pd.DataFrame:
    """Table des organes (groupes politiques, commissions, circonscriptions)."""
    lignes = []
    for org in _charger(config.INTERIM / "an_acteurs" / "json" / "organe", "organe"):
        vimode = org.get("viMoDe") or {}
        lignes.append({
            "organe_ref": _txt(org.get("uid")),
            "type_organe": _txt(org.get("codeType")),
            "libelle": _txt(org.get("libelle")),
            "abrev": _txt(org.get("libelleAbrev")),
            "date_debut": _txt(vimode.get("dateDebut")),
            "date_fin": _txt(vimode.get("dateFin")),
        })
    df = pd.DataFrame(lignes)
    logger.info("organes : %d lignes, %d groupes politiques",
                len(df), (df["type_organe"] == "GP").sum())
    return df


def _mandat_groupe_actif(mandats: list[dict]) -> dict | None:
    """Dernier mandat de groupe politique commencé (le groupe courant du député)."""
    gp = [m for m in mandats
          if _txt(m.get("typeOrgane")) == "GP" and _txt(m.get("legislature")) == config.LEGISLATURE]
    if not gp:
        return None
    return max(gp, key=lambda m: (_txt(m.get("dateFin")) is None, _txt(m.get("dateDebut")) or ""))


def charger_deputes(organes: pd.DataFrame | None = None) -> pd.DataFrame:
    """Un député de la XVIIe législature par ligne."""
    organes = charger_organes() if organes is None else organes
    lib_organe = organes.set_index("organe_ref")["libelle"].to_dict()
    abr_organe = organes.set_index("organe_ref")["abrev"].to_dict()

    lignes = []
    for act in _charger(config.INTERIM / "an_acteurs" / "json" / "acteur", "acteur"):
        mandats = _liste((act.get("mandats") or {}).get("mandat"))
        parlementaires = [
            m for m in mandats
            if _txt(m.get("typeOrgane")) == "ASSEMBLEE"
            and _txt(m.get("legislature")) == config.LEGISLATURE
        ]
        if not parlementaires:
            continue  # sénateurs, ministres, anciens députés d'autres législatures

        mandat = max(parlementaires, key=lambda m: _txt(m.get("dateDebut")) or "")
        ident = ((act.get("etatCivil") or {}).get("ident")) or {}
        naissance = ((act.get("etatCivil") or {}).get("infoNaissance")) or {}
        election = (mandat.get("election") or {}).get("lieu") or {}
        mandature = mandat.get("mandature") or {}
        groupe = _mandat_groupe_actif(mandats)
        groupe_ref = _txt(((groupe or {}).get("organes") or {}).get("organeRef"))

        commissions = sorted({
            lib_organe.get(_txt((m.get("organes") or {}).get("organeRef")), "")
            for m in mandats
            if _txt(m.get("typeOrgane")) in {"COMPER", "COMNL"}
            and _txt(m.get("dateFin")) is None
        } - {""})

        lignes.append({
            "acteur_ref": _txt(act.get("uid")),
            "civilite": _txt(ident.get("civ")),
            "prenom": _txt(ident.get("prenom")),
            "nom": _txt(ident.get("nom")),
            "trigramme": _txt(ident.get("trigramme")),
            "date_naissance": _txt(naissance.get("dateNais")),
            "profession": _txt((act.get("profession") or {}).get("libelleCourant")),
            "categorie_socpro": _txt(
                ((act.get("profession") or {}).get("socProcINSEE") or {}).get("catSocPro")),
            "uri_hatvp": _txt(act.get("uri_hatvp")),
            "groupe_ref": groupe_ref,
            "groupe": lib_organe.get(groupe_ref),
            "groupe_abrev": abr_organe.get(groupe_ref),
            "region": _txt(election.get("region")),
            "departement": _txt(election.get("departement")),
            "num_departement": _txt(election.get("numDepartement")),
            "num_circo": _txt(election.get("numCirco")),
            "premiere_election": _txt(mandature.get("premiereElection")),
            "mandat_debut": _txt(mandat.get("dateDebut")),
            "mandat_fin": _txt(mandat.get("dateFin")),
            "commissions": " | ".join(commissions),
        })

    df = pd.DataFrame(lignes).drop_duplicates("acteur_ref")
    df["nom_complet"] = (df["prenom"].fillna("") + " " + df["nom"].fillna("")).str.strip()
    df["nom_normalise"] = df["nom_complet"].map(normaliser)
    df["bloc"] = df["groupe_abrev"].map(config.BLOCS_POLITIQUES).fillna("autre")
    df["en_exercice"] = df["mandat_fin"].isna()
    logger.info("deputes : %d lignes (%d en exercice), %d groupes",
                len(df), int(df["en_exercice"].sum()), df["groupe_abrev"].nunique())
    return df


# --------------------------------------------------------------------------
# Dossiers législatifs
# --------------------------------------------------------------------------


def _parcourir_actes(acte: Any) -> Iterator[dict]:
    """Aplatit l'arbre récursif des actes législatifs d'un dossier."""
    for noeud in _liste(acte):
        if not isinstance(noeud, dict):
            continue
        yield noeud
        enfants = (noeud.get("actesLegislatifs") or {})
        if isinstance(enfants, dict):
            yield from _parcourir_actes(enfants.get("acteLegislatif"))


def charger_dossiers() -> pd.DataFrame:
    """Un dossier législatif par ligne, avec sa fenêtre de débat et ses textes."""
    lignes = []
    base = config.INTERIM / "an_dossiers" / "json" / "dossierParlementaire"
    for dos in _charger(base, "dossierParlementaire"):
        if _txt(dos.get("legislature")) != config.LEGISLATURE:
            continue
        titre_bloc = dos.get("titreDossier") or {}
        actes = list(_parcourir_actes((dos.get("actesLegislatifs") or {}).get("acteLegislatif")))
        dates = sorted(d for d in (_txt(a.get("dateActe")) for a in actes) if d)
        textes = sorted({t for t in (_txt(a.get("texteAssocie")) for a in actes) if t})
        lignes.append({
            "dossier_ref": _txt(dos.get("uid")),
            "titre": _txt(titre_bloc.get("titre")),
            "titre_chemin": _txt(titre_bloc.get("titreChemin")),
            "procedure": _txt((dos.get("procedureParlementaire") or {}).get("libelle")),
            "date_premier_acte": dates[0][:10] if dates else None,
            "date_dernier_acte": dates[-1][:10] if dates else None,
            "nb_actes": len(actes),
            "textes_associes": " | ".join(textes),
        })
    df = pd.DataFrame(lignes)
    df["titre_normalise"] = df["titre"].map(normaliser)
    logger.info("dossiers : %d lignes", len(df))
    return df


def table_textes_dossiers(dossiers: pd.DataFrame) -> pd.DataFrame:
    """Dépliage ``texteLegislatifRef -> dossier_ref`` (clé de jointure des amendements)."""
    paires = (
        dossiers.assign(texte_ref=dossiers["textes_associes"].str.split(" | ", regex=False))
        .explode("texte_ref")
        .dropna(subset=["texte_ref"])
        .loc[:, ["texte_ref", "dossier_ref", "titre"]]
        .query("texte_ref != ''")
        .drop_duplicates("texte_ref")
        .reset_index(drop=True)
    )
    logger.info("correspondance texte législatif -> dossier : %d entrées", len(paires))
    return paires


# --------------------------------------------------------------------------
# Scrutins et votes nominatifs
# --------------------------------------------------------------------------

_POSITIONS = {"pours": "pour", "contres": "contre",
              "abstentions": "abstention", "nonVotants": "non votant"}


def charger_scrutins() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retourne ``(scrutins, votes)``.

    ``votes`` est la table longue : une ligne par (scrutin, député, position).
    """
    scrutins, votes = [], []
    base = config.INTERIM / "an_scrutins" / "json"
    for scr in _charger(base, "scrutin"):
        uid = _txt(scr.get("uid"))
        objet = scr.get("objet") or {}
        dossier = objet.get("dossierLegislatif") or {}
        synthese = scr.get("syntheseVote") or {}
        decompte = synthese.get("decompte") or {}
        scrutins.append({
            "scrutin_uid": uid,
            "numero": _txt(scr.get("numero")),
            "date_scrutin": _txt(scr.get("dateScrutin")),
            "titre": _txt(scr.get("titre")),
            "type_vote": _txt((scr.get("typeVote") or {}).get("libelleTypeVote")),
            "sort": _txt((scr.get("sort") or {}).get("code")),
            "demandeur": _txt((scr.get("demandeur") or {}).get("texte")),
            "dossier_ref_declare": _txt(dossier.get("dossierRef")),
            "dossier_libelle_declare": _txt(dossier.get("libelle")),
            "nb_votants": pd.to_numeric(_txt(synthese.get("nombreVotants")), errors="coerce"),
            "nb_pour": pd.to_numeric(_txt(decompte.get("pour")), errors="coerce"),
            "nb_contre": pd.to_numeric(_txt(decompte.get("contre")), errors="coerce"),
            "nb_abstention": pd.to_numeric(_txt(decompte.get("abstentions")), errors="coerce"),
        })

        organe = ((scr.get("ventilationVotes") or {}).get("organe")) or {}
        for groupe in _liste((organe.get("groupes") or {}).get("groupe")):
            groupe_ref = _txt(groupe.get("organeRef"))
            vote = groupe.get("vote") or {}
            nominatif = vote.get("decompteNominatif") or {}
            for champ, position in _POSITIONS.items():
                for votant in _liste((nominatif.get(champ) or {}).get("votant")):
                    votes.append({
                        "scrutin_uid": uid,
                        "acteur_ref": _txt(votant.get("acteurRef")),
                        "groupe_ref_vote": groupe_ref,
                        "position": position,
                        "par_delegation": _txt(votant.get("parDelegation")) == "true",
                        "position_majoritaire_groupe": _txt(vote.get("positionMajoritaire")),
                    })

    df_scr = pd.DataFrame(scrutins).sort_values("date_scrutin").reset_index(drop=True)
    df_votes = pd.DataFrame(votes)
    logger.info("scrutins : %d ; votes nominatifs : %d", len(df_scr), len(df_votes))
    return df_scr, df_votes


# --------------------------------------------------------------------------
# Amendements
# --------------------------------------------------------------------------


def charger_amendements(*, avec_texte: bool = True) -> pd.DataFrame:
    """Un amendement par ligne.

    `avec_texte=True` conserve le dispositif et l'exposé sommaire en texte brut :
    c'est la matière première du rapprochement avec l'objet déclaré des lobbies.
    """
    lignes = []
    base = config.INTERIM / "an_amendements"
    for amd in _charger(base, "amendement"):
        signataires = amd.get("signataires") or {}
        auteur = signataires.get("auteur") or {}
        cycle = amd.get("cycleDeVie") or {}
        etats = (cycle.get("etatDesTraitements") or {})
        pointeur = (amd.get("pointeurFragmentTexte") or {}).get("division") or {}
        contenu = ((amd.get("corps") or {}).get("contenuAuteur")) or {}
        cosignataires = _liste(((signataires.get("cosignataires") or {}).get("acteurRef")))

        ligne = {
            "amendement_uid": _txt(amd.get("uid")),
            "numero_long": _txt((amd.get("identification") or {}).get("numeroLong")),
            "texte_ref": _txt(amd.get("texteLegislatifRef")),
            "examen_ref": _txt(amd.get("examenRef")),
            "organe_examen": _txt((amd.get("identification") or {}).get("prefixeOrganeExamen")),
            "type_auteur": _txt(auteur.get("typeAuteur")),
            "acteur_ref": _txt(auteur.get("acteurRef")),
            "groupe_ref_auteur": _txt(auteur.get("groupePolitiqueRef")),
            "nb_cosignataires": len([c for c in cosignataires if isinstance(c, str)]),
            "date_depot": _txt(cycle.get("dateDepot")),
            "sort": _txt(cycle.get("sort")),
            "etat": _txt((etats.get("etat") or {}).get("libelle")),
            "article_vise": _txt(pointeur.get("articleDesignation")),
            "type_division": _txt(pointeur.get("type")),
            "article_additionnel": _txt(pointeur.get("articleAdditionnel")) == "true",
        }
        if avec_texte:
            ligne["dispositif"] = nettoyer_html(_txt(contenu.get("dispositif")))
            ligne["expose"] = nettoyer_html(_txt(contenu.get("exposeSommaire")))
        lignes.append(ligne)

    df = pd.DataFrame(lignes)
    df["adopte"] = df["sort"].eq("Adopté")
    logger.info("amendements : %d lignes (%d adoptés, %d auteurs députés)",
                len(df), int(df["adopte"].sum()), df["acteur_ref"].nunique())
    return df


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def construire_tables_an(*, ecrire: bool = True) -> dict[str, pd.DataFrame]:
    """Produit les tables Assemblée et les écrit en parquet dans `data/processed`."""
    organes = charger_organes()
    tables = {
        "an_organes": organes,
        "an_deputes": charger_deputes(organes),
        "an_dossiers": charger_dossiers(),
    }
    tables["an_textes_dossiers"] = table_textes_dossiers(tables["an_dossiers"])
    tables["an_scrutins"], tables["an_votes"] = charger_scrutins()
    tables["an_amendements"] = charger_amendements()

    if ecrire:
        for nom, df in tables.items():
            chemin = config.PROCESSED / f"{nom}.parquet"
            df.to_parquet(chemin, index=False)
            logger.info("écrit %s (%d lignes, %.1f Mo)",
                        chemin.name, len(df), chemin.stat().st_size / 1e6)
    return tables


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    construire_tables_an()

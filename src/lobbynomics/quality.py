"""Contrôles de qualité des données.

Une erreur de parsing produit une exception, qu'on voit. Une erreur de données
produit un tableau plausible et faux, qu'on ne voit pas. Ce module écrit noir sur
blanc ce qu'on attend des tables, et vérifie que c'est vrai — identifiants
uniques, intégrité référentielle entre tables, cohérence interne des décomptes de
votes, plages de dates, taux de valeurs manquantes.

Chaque contrôle renvoie un statut :

``ok``      la table se comporte comme annoncé ;
``alerte``  un écart existe, il est attendu et expliqué (par exemple les mises au
            point de vote, qui créent un décalage normal entre le décompte
            officiel d'un scrutin et le détail nominatif) ;
``echec``   un écart qui invalide une analyse ; le pipeline doit s'arrêter.

Le rapport produit par `controler_tout` est publié dans le notebook : un lecteur
n'a pas à croire sur parole que les données sont propres.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

import pandas as pd

from . import config

logger = logging.getLogger(__name__)

OK, ALERTE, ECHEC = "ok", "alerte", "echec"


def _controle(nom: str, portee: str, constat: str, statut: str,
              commentaire: str = "") -> dict:
    return {"contrôle": nom, "portée": portee, "constat": constat,
            "statut": statut, "commentaire": commentaire}


# --------------------------------------------------------------------------
# Contrôles élémentaires
# --------------------------------------------------------------------------


def unicite(df: pd.DataFrame, colonne: str, nom_table: str) -> dict:
    """Un identifiant doit identifier une ligne et une seule."""
    doublons = int(df[colonne].duplicated().sum())
    manquants = int(df[colonne].isna().sum())
    statut = OK if doublons == 0 and manquants == 0 else ECHEC
    return _controle(
        f"unicité de {colonne}", nom_table,
        f"{len(df):,} lignes, {doublons} doublon(s), {manquants} valeur(s) manquante(s)".replace(",", " "),
        statut,
        "" if statut == OK else "un identifiant dupliqué fausse toutes les jointures")


def integrite(enfant: pd.DataFrame, cle_enfant: str, parent: pd.DataFrame,
              cle_parent: str, nom: str, *, tolerance: float = 0.0) -> dict:
    """Les clés étrangères d'une table doivent exister dans la table de référence."""
    valeurs = enfant[cle_enfant].dropna()
    connues = set(parent[cle_parent].dropna())
    orphelines = valeurs[~valeurs.isin(connues)]
    taux = len(orphelines) / len(valeurs) if len(valeurs) else 0.0
    statut = OK if taux <= tolerance else (ALERTE if taux <= 0.05 else ECHEC)
    return _controle(
        f"intégrité {cle_enfant} → {cle_parent}", nom,
        f"{len(orphelines):,} clé(s) orpheline(s) sur {len(valeurs):,} ({100 * taux:.2f} %)".replace(",", " "),
        statut,
        "" if statut == OK else f"{orphelines.nunique()} valeur(s) distincte(s) sans correspondance")


def completude(df: pd.DataFrame, colonnes: list[str], nom_table: str,
               *, seuil_alerte: float = 0.10) -> list[dict]:
    """Taux de valeurs manquantes sur les colonnes dont dépend l'analyse."""
    controles = []
    for colonne in colonnes:
        if colonne not in df.columns:
            controles.append(_controle(f"présence de {colonne}", nom_table,
                                       "colonne absente", ECHEC))
            continue
        taux = float(df[colonne].isna().mean())
        statut = OK if taux == 0 else (ALERTE if taux <= seuil_alerte else ECHEC)
        controles.append(_controle(
            f"complétude de {colonne}", nom_table, f"{100 * taux:.1f} % manquants", statut))
    return controles


def plage_dates(df: pd.DataFrame, colonne: str, nom_table: str,
                debut: str, fin: str) -> dict:
    """Les dates doivent tomber dans la fenêtre de la législature étudiée."""
    dates = pd.to_datetime(df[colonne], errors="coerce").dropna()
    hors = int(((dates < pd.Timestamp(debut)) | (dates > pd.Timestamp(fin))).sum())
    statut = OK if hors == 0 else ALERTE
    return _controle(
        f"plage de {colonne}", nom_table,
        f"{dates.min().date()} → {dates.max().date()}, {hors} hors fenêtre [{debut} ; {fin}]",
        statut, "" if statut == OK else "dates hors législature : vérifier le filtrage")


def coherence_decomptes(scrutins: pd.DataFrame, votes: pd.DataFrame) -> dict:
    """Le décompte officiel d'un scrutin doit correspondre au détail nominatif.

    Un écart est attendu : les « mises au point » permettent à un député de faire
    rectifier son vote après coup sans que le résultat du scrutin change. Le
    contrôle sert donc à mesurer l'ampleur du phénomène, pas à l'interdire.
    """
    nominatif = (votes[votes["position"].isin(["pour", "contre"])]
                 .pivot_table(index="scrutin_uid", columns="position",
                              values="acteur_ref", aggfunc="size")
                 .rename(columns={"pour": "nominatif_pour", "contre": "nominatif_contre"}))
    fusion = scrutins.set_index("scrutin_uid")[["nb_pour", "nb_contre"]].join(nominatif, how="inner")
    fusion = fusion.dropna()
    ecart = ((fusion["nb_pour"] != fusion["nominatif_pour"])
             | (fusion["nb_contre"] != fusion["nominatif_contre"]))
    taux = float(ecart.mean()) if len(fusion) else 0.0
    statut = OK if taux == 0 else (ALERTE if taux <= 0.25 else ECHEC)
    return _controle(
        "cohérence décompte officiel / détail nominatif", "an_scrutins × an_votes",
        f"{int(ecart.sum()):,} scrutin(s) en écart sur {len(fusion):,} ({100 * taux:.1f} %)".replace(",", " "),
        statut,
        "écart attendu : les mises au point de vote modifient le détail nominatif "
        "sans changer le résultat proclamé")


def couverture_rattachement(scrutins: pd.DataFrame) -> dict:
    """Part des scrutins reliés à un dossier législatif."""
    if "origine_lien" not in scrutins.columns:
        return _controle("couverture du rattachement", "scrutins_rattaches",
                         "colonne origine_lien absente", ECHEC)
    repartition = scrutins["origine_lien"].value_counts()
    taux = 1 - repartition.get("aucun", 0) / len(scrutins)
    statut = OK if taux >= 0.85 else (ALERTE if taux >= 0.7 else ECHEC)
    return _controle(
        "couverture du rattachement scrutin → dossier", "scrutins_rattaches",
        f"{100 * taux:.1f} % rattachés "
        f"({repartition.get('declare', 0)} déclarés, {repartition.get('fuzzy', 0)} inférés)",
        statut, "les non rattachés sont des titres qui ne nomment aucun texte")


def ciblage_non_vide(ciblage: pd.DataFrame) -> list[dict]:
    """Chaque texte analysé doit avoir au moins quelques activités de niveau 1."""
    controles = []
    for cle in config.TEXTES_ANALYSE:
        n = int(ciblage.loc[ciblage["texte_cle"].eq(cle), "cible_nommee"].sum())
        statut = OK if n >= 10 else (ALERTE if n >= 3 else ECHEC)
        controles.append(_controle(
            f"activités de niveau 1 — {cle}", "ciblage_hatvp",
            f"{n} activité(s) nommant le texte", statut,
            "" if statut == OK else "effectif trop faible pour une mesure stable"))
    return controles


def equilibre_variable(df: pd.DataFrame, colonne: str, nom_table: str,
                       *, minimum: float = 0.02) -> dict:
    """Une variable binaire quasi constante ne peut rien expliquer."""
    part = float(pd.to_numeric(df[colonne], errors="coerce").mean())
    statut = OK if minimum <= part <= 1 - minimum else ALERTE
    return _controle(
        f"variabilité de {colonne}", nom_table, f"{100 * part:.2f} % de positifs", statut,
        "" if statut == OK else "variable trop déséquilibrée pour être identifiée")



def coherence_sort_etat(amendements: pd.DataFrame) -> dict:
    """Le sort d'un amendement n'existe que s'il a été discuté.

    44 % des amendements n'ont pas de sort : un seuil générique de complétude
    criait à l'échec. En réalité la relation est exacte — un amendement
    « A discuter », « En traitement », « Irrecevable » ou « Retiré » n'a pas
    encore de sort. Le contrôle vérifie donc l'équivalence, pas un taux.
    """
    discute = amendements["etat"].eq("Discuté")
    a_un_sort = amendements["sort"].notna()
    violations = int((discute != a_un_sort).sum())
    statut = OK if violations == 0 else ECHEC
    return _controle(
        "sort renseigné si et seulement si l'amendement a été discuté", "an_amendements",
        f"{int(discute.sum()):,} discutés, {int(a_un_sort.sum()):,} avec sort, "
        f"{violations} incohérence(s)".replace(",", " "),
        statut,
        "les 44 % sans sort sont des amendements non discutés (irrecevables, "
        "retirés, en attente) : c'est une absence attendue, pas une donnée perdue")


def coherence_auteur(amendements: pd.DataFrame) -> dict:
    """Seuls les amendements du Gouvernement sont sans auteur individuel.

    Quatre exceptions subsistent sur 126 392 lignes : des amendements à l'état
    « effacé », dont l'auteur a été retiré de la base en même temps que le
    contenu. Elles sont exclues du contrôle plutôt que tolérées en silence —
    quatre lignes inexpliquées suffisent à faire douter du reste.
    """
    examinables = amendements[amendements["etat"].ne("effacé")]
    gouvernement = examinables["type_auteur"].eq("Gouvernement")
    sans_acteur = examinables["acteur_ref"].isna()
    violations = int((gouvernement != sans_acteur).sum())
    effaces = int(amendements["etat"].eq("effacé").sum())
    statut = OK if violations == 0 else ECHEC
    return _controle(
        "auteur individuel absent si et seulement si l'amendement est gouvernemental",
        "an_amendements",
        f"{int(gouvernement.sum()):,} amendements du Gouvernement, "
        f"{violations} incohérence(s), {effaces} amendement(s) effacé(s) exclu(s)".replace(",", " "),
        statut, "un amendement du Gouvernement n'a pas d'auteur député : c'est normal")


def dossiers_hors_legislature(scrutins: pd.DataFrame, dossiers: pd.DataFrame) -> dict:
    """Les dossiers introuvables doivent tous venir d'une législature antérieure.

    Douze scrutins de la XVIIe législature pointent vers un dossier absent du
    fichier. Vérification faite, leurs identifiants commencent tous par
    ``DLR5L16`` : ce sont des textes ouverts sous la XVIe et achevés sous la
    XVIIe. Rien n'est cassé ; le jeu de données téléchargé s'arrête simplement à
    la législature en cours.
    """
    connus = set(dossiers["dossier_ref"].dropna())
    orphelins = scrutins.loc[scrutins["dossier_ref"].notna()
                             & ~scrutins["dossier_ref"].isin(connus), "dossier_ref"]
    prefixe_attendu = f"DLR5L{int(config.LEGISLATURE) - 1}"
    anciens = orphelins.str.startswith(prefixe_attendu)
    statut = OK if orphelins.empty or bool(anciens.all()) else ALERTE
    return _controle(
        "dossiers introuvables issus de la législature précédente", "scrutins_rattaches",
        f"{len(orphelins)} scrutin(s), {orphelins.nunique()} dossier(s) distinct(s), "
        f"{int(anciens.sum())} au préfixe {prefixe_attendu}",
        statut,
        "textes entamés sous la législature précédente : le fichier téléchargé "
        "ne couvre que la législature en cours")


# --------------------------------------------------------------------------
# Rapport complet
# --------------------------------------------------------------------------


def controler_tout(lire: Callable[[str], pd.DataFrame]) -> pd.DataFrame:
    """Exécute tous les contrôles et retourne un rapport ordonné par gravité.

    `lire` est la fonction de lecture des tables (injectée pour que ce module ne
    dépende ni du pipeline ni du notebook).
    """
    deputes, scrutins = lire("an_deputes"), lire("an_scrutins")
    votes, amendements = lire("an_votes"), lire("an_amendements")
    dossiers, organisations = lire("an_dossiers"), lire("hatvp_organisations")
    rattaches, ciblage = lire("scrutins_rattaches"), lire("ciblage_hatvp")
    dissidence = lire("analyse_dissidence")

    controles: list[dict] = [
        unicite(deputes, "acteur_ref", "an_deputes"),
        unicite(scrutins, "scrutin_uid", "an_scrutins"),
        unicite(amendements, "amendement_uid", "an_amendements"),
        unicite(dossiers, "dossier_ref", "an_dossiers"),
        unicite(organisations, "identifiant_national", "hatvp_organisations"),
        integrite(votes, "acteur_ref", deputes, "acteur_ref", "an_votes → an_deputes"),
        integrite(votes, "scrutin_uid", scrutins, "scrutin_uid", "an_votes → an_scrutins"),
        dossiers_hors_legislature(rattaches, dossiers),
        coherence_sort_etat(amendements),
        coherence_auteur(amendements),
        coherence_decomptes(scrutins, votes),
        couverture_rattachement(rattaches),
        plage_dates(scrutins, "date_scrutin", "an_scrutins", "2024-07-01", "2029-12-31"),
        plage_dates(amendements, "date_depot", "an_amendements", "2024-07-01", "2029-12-31"),
        equilibre_variable(dissidence, "dissident", "analyse_dissidence"),
    ]
    controles += completude(deputes, ["acteur_ref", "nom_complet", "groupe_abrev",
                                      "departement"], "an_deputes")
    controles += completude(amendements, ["texte_ref", "etat"], "an_amendements")
    controles += ciblage_non_vide(ciblage)

    rapport = pd.DataFrame(controles)
    ordre = {ECHEC: 0, ALERTE: 1, OK: 2}
    rapport = (rapport.assign(_o=rapport["statut"].map(ordre))
               .sort_values(["_o", "portée"]).drop(columns="_o").reset_index(drop=True))
    compte = rapport["statut"].value_counts().to_dict()
    logger.info("contrôles qualité : %s", compte)
    if compte.get(ECHEC):
        logger.error("%d contrôle(s) en échec — les analyses en aval sont suspectes",
                     compte[ECHEC])
    return rapport


def echecs(rapport: pd.DataFrame) -> pd.DataFrame:
    """Sous-ensemble bloquant du rapport."""
    return rapport[rapport["statut"].eq(ECHEC)]

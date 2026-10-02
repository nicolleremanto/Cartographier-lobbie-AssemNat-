"""Étape 4 — construction de la table d'analyse.

Une ligne = un député × un texte de loi. C'est le tableau final annoncé dans le
plan de travail : ``député | groupe | texte | exposition au lobbying | sens du
vote``, enrichi des contrôles.

Le point délicat, et c'est le cœur méthodologique du projet : le répertoire HATVP
ne nomme **jamais** le député approché. Il dit « j'ai contacté des députés sur ce
sujet ». Une variable d'exposition au lobbying propre à chaque député ne peut
donc pas être lue dans les données ; il faut la construire. On le fait par la
**proximité lexicale** entre ce que le député a écrit dans ses amendements sur le
texte et ce que les lobbies du secteur ont déclaré vouloir obtenir.

Ce n'est pas une mesure de contact. C'est une mesure de **convergence de
discours**, qui peut venir d'une influence comme d'une conviction préexistante,
voire de l'usage d'un vocabulaire technique commun à tout le secteur. Le rapport
le dit explicitement ; la régression ne prétend pas trancher.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from . import config, matching
from .parse_an import normaliser

logger = logging.getLogger(__name__)

#: Mots vides français utiles : le vocabulaire parlementaire est très répétitif
#: (« amendement », « article », « alinéa »…) et sature sinon la similarité.
MOTS_VIDES = [
    "le", "la", "les", "de", "des", "du", "un", "une", "et", "ou", "a", "au", "aux",
    "en", "dans", "par", "pour", "sur", "que", "qui", "ne", "pas", "plus", "est",
    "sont", "etre", "avoir", "ce", "cet", "cette", "ces", "se", "sa", "son", "ses",
    "il", "elle", "ils", "elles", "on", "nous", "vous", "leur", "leurs", "y",
    "d", "l", "s", "n", "c", "qu", "amendement", "amendements", "article",
    "articles", "alinea", "alineas", "loi", "projet", "proposition", "texte",
    "assemblee", "nationale", "present", "presente", "vise", "visant", "objet",
    "cadre", "mise", "oeuvre", "ainsi", "donc", "afin", "notamment", "egalement",
    "faire", "fait", "etc", "mme", "mm", "rapporteur", "commission", "seance",
]


# --------------------------------------------------------------------------
# Repérage du scrutin décisif
# --------------------------------------------------------------------------


def scrutins_ensemble(scrutins: pd.DataFrame, texte: config.TexteCible) -> pd.DataFrame:
    """Scrutins portant sur l'ensemble du texte, du plus ancien au plus récent.

    Les centaines d'autres scrutins du dossier portent sur des amendements : les
    agréger n'aurait pas de sens (voter contre un amendement peut vouloir dire
    soutenir le texte). Le vote sur l'ensemble est le seul qui exprime une
    position sur le texte lui-même.
    """
    du_dossier = scrutins[scrutins["dossier_ref"] == texte.dossier_ref]
    ensemble = du_dossier[du_dossier["titre"].str.contains(
        r"l'ensemble (?:du|de la)", case=False, na=False, regex=True)]
    return ensemble.sort_values("date_scrutin")


# --------------------------------------------------------------------------
# Exposition au lobbying, mesurée par proximité lexicale
# --------------------------------------------------------------------------


def _corpus_amendements(amendements: pd.DataFrame) -> pd.DataFrame:
    """Un document par député : la concaténation de ses exposés des motifs."""
    amendements = amendements[amendements["type_auteur"].eq("Député")
                              & amendements["acteur_ref"].notna()].copy()
    amendements["document"] = (
        amendements["expose"].fillna("") + " " + amendements["dispositif"].fillna("")
    ).map(normaliser)
    par_depute = (amendements.groupby("acteur_ref")
                  .agg(document=("document", " ".join),
                       nb_amendements=("amendement_uid", "size"),
                       nb_amendements_adoptes=("adopte", "sum"))
                  .reset_index())
    return par_depute


def proximite_lobbies(amendements_texte: pd.DataFrame, ciblage_texte: pd.DataFrame,
                      *, min_caracteres: int = 200) -> pd.DataFrame:
    """Proximité lexicale entre les amendements de chaque député et les objets
    déclarés des lobbies ciblant le texte.

    Méthode : un seul espace TF-IDF est appris sur l'union des deux corpus
    (sinon les deux vocabulaires ne sont pas comparables), puis on calcule les
    cosinus entre chaque député et chaque activité de lobbying retenue.

    Retourne, par député : la proximité maximale, la proximité moyenne des cinq
    activités les plus proches, et le nom du lobby le plus proche — ce dernier
    sert à construire le graphe biparti.
    """
    deputes = _corpus_amendements(amendements_texte)
    deputes = deputes[deputes["document"].str.len() >= min_caracteres]
    objets = ciblage_texte.loc[ciblage_texte["cible_texte"], ["activite_id", "denomination", "objet"]].copy()
    objets["document"] = objets["objet"].fillna("").map(normaliser)
    objets = objets[objets["document"].str.len() > 20].drop_duplicates("document")

    if deputes.empty or objets.empty:
        logger.warning("proximité impossible : %d députés, %d objets de lobbying",
                       len(deputes), len(objets))
        return pd.DataFrame(columns=["acteur_ref", "proximite_max", "proximite_top5",
                                     "lobby_le_plus_proche", "nb_amendements",
                                     "nb_amendements_adoptes"])

    vectoriseur = TfidfVectorizer(
        stop_words=MOTS_VIDES, ngram_range=(1, 2), min_df=2, max_df=0.8,
        sublinear_tf=True, norm="l2",
    )
    vectoriseur.fit(pd.concat([deputes["document"], objets["document"]]))
    md = vectoriseur.transform(deputes["document"])
    mo = vectoriseur.transform(objets["document"])
    similarites = (md @ mo.T).toarray()          # matrices L2-normalisées → cosinus

    ordre = np.argsort(-similarites, axis=1)
    top5 = np.take_along_axis(similarites, ordre[:, :5], axis=1)
    resultat = deputes[["acteur_ref", "nb_amendements", "nb_amendements_adoptes"]].copy()
    resultat["proximite_max"] = similarites.max(axis=1)
    resultat["proximite_top5"] = top5.mean(axis=1)
    resultat["lobby_le_plus_proche"] = objets["denomination"].to_numpy()[ordre[:, 0]]
    logger.info("proximité lexicale : %d députés × %d objets de lobbying "
                "(proximité max médiane %.3f)",
                len(deputes), len(objets), resultat["proximite_max"].median())
    return resultat


def aretes_biparties(amendements_texte: pd.DataFrame, ciblage_texte: pd.DataFrame,
                     *, seuil: float = 0.08, max_par_depute: int = 3) -> pd.DataFrame:
    """Arêtes « lobby ↔ député » du graphe biparti, pondérées par la proximité.

    On ne garde que les quelques meilleures arêtes par député au-dessus d'un
    seuil : un graphe complet de 600 × 900 nœuds n'apprend rien à personne.
    """
    deputes = _corpus_amendements(amendements_texte)
    deputes = deputes[deputes["document"].str.len() >= 200]
    objets = ciblage_texte.loc[ciblage_texte["cible_texte"],
                               ["activite_id", "denomination", "categorie_famille", "objet"]].copy()
    objets["document"] = objets["objet"].fillna("").map(normaliser)
    objets = objets[objets["document"].str.len() > 20].drop_duplicates("document")
    if deputes.empty or objets.empty:
        return pd.DataFrame(columns=["acteur_ref", "denomination", "categorie_famille", "poids"])

    vectoriseur = TfidfVectorizer(stop_words=MOTS_VIDES, ngram_range=(1, 2),
                                  min_df=2, max_df=0.8, sublinear_tf=True)
    vectoriseur.fit(pd.concat([deputes["document"], objets["document"]]))
    sim = (vectoriseur.transform(deputes["document"])
           @ vectoriseur.transform(objets["document"]).T).toarray()

    lignes = []
    denominations = objets["denomination"].to_numpy()
    familles = objets["categorie_famille"].to_numpy()
    for i, acteur in enumerate(deputes["acteur_ref"].to_numpy()):
        meilleurs = np.argsort(-sim[i])[:max_par_depute]
        for j in meilleurs:
            if sim[i, j] >= seuil:
                lignes.append({"acteur_ref": acteur, "denomination": denominations[j],
                               "categorie_famille": familles[j], "poids": float(sim[i, j])})
    aretes = (pd.DataFrame(lignes)
              .groupby(["acteur_ref", "denomination", "categorie_famille"], as_index=False)
              .agg(poids=("poids", "max")))
    logger.info("graphe biparti : %d arêtes, %d députés, %d organisations",
                len(aretes), aretes["acteur_ref"].nunique() if len(aretes) else 0,
                aretes["denomination"].nunique() if len(aretes) else 0)
    return aretes


# --------------------------------------------------------------------------
# Table d'analyse
# --------------------------------------------------------------------------


def table_analyse(*, scrutins: pd.DataFrame, votes: pd.DataFrame,
                  deputes_hatvp: pd.DataFrame, amendements: pd.DataFrame,
                  ciblage: pd.DataFrame, departements: pd.DataFrame,
                  textes: tuple[str, ...] | None = None,
                  rang_scrutin: int = 0) -> pd.DataFrame:
    """Assemble la table député × texte.

    `rang_scrutin` choisit lequel des votes sur l'ensemble est pris comme
    variable expliquée : 0 = première lecture (retenu par défaut, c'est le vote
    le plus suivi), 1 = lecture suivante, utilisée en test de robustesse.
    """
    cles = config.TEXTES_ANALYSE if textes is None else textes
    densites = departements.set_index("departement_normalise")[
        ["densite_hab_km2", "part_rurale"]]

    morceaux = []
    for cle in cles:
        texte = config.TEXTES_PAR_CLE[cle]
        ensemble = scrutins_ensemble(scrutins, texte)
        if len(ensemble) <= rang_scrutin:
            logger.warning("[%s] pas de scrutin sur l'ensemble au rang %d", cle, rang_scrutin)
            continue
        scrutin = ensemble.iloc[rang_scrutin]

        v = votes[votes["scrutin_uid"] == scrutin["scrutin_uid"]].copy()
        amendements_texte = amendements[amendements["dossier_ref"] == texte.dossier_ref]
        ciblage_texte = ciblage[ciblage["texte_cle"] == cle]

        prox = proximite_lobbies(amendements_texte, ciblage_texte)
        amd_par_depute = (amendements_texte[amendements_texte["type_auteur"].eq("Député")]
                          .groupby("acteur_ref", as_index=False)
                          .agg(nb_amendements_texte=("amendement_uid", "size"),
                               nb_amendements_adoptes_texte=("adopte", "sum")))

        df = (v.merge(deputes_hatvp, on="acteur_ref", how="left")
              .merge(prox.drop(columns=["nb_amendements", "nb_amendements_adoptes"]),
                     on="acteur_ref", how="left")
              .merge(amd_par_depute, on="acteur_ref", how="left"))

        df["texte_cle"] = cle
        df["texte_libelle"] = texte.libelle
        df["scrutin_uid"] = scrutin["scrutin_uid"]
        df["date_scrutin"] = scrutin["date_scrutin"]
        df["numero_scrutin"] = scrutin["numero"]

        df["vote_pour"] = df["position"].map({"pour": 1, "contre": 0})
        df["a_vote"] = df["position"].isin(["pour", "contre"])
        df["nb_amendements_texte"] = df["nb_amendements_texte"].fillna(0).astype(int)
        df["nb_amendements_adoptes_texte"] = df["nb_amendements_adoptes_texte"].fillna(0).astype(int)
        df["a_depose_amendement"] = df["nb_amendements_texte"] > 0
        df["proximite_max"] = df["proximite_max"].fillna(0.0)
        df["proximite_top5"] = df["proximite_top5"].fillna(0.0)
        df["interet_sectoriel_declare"] = matching.interet_sectoriel(df, texte)

        contexte = df["departement"].map(normaliser).map(densites.to_dict("index"))
        df["densite_hab_km2"] = contexte.map(
            lambda d: d["densite_hab_km2"] if isinstance(d, dict) else np.nan)
        df["part_rurale"] = contexte.map(
            lambda d: d["part_rurale"] if isinstance(d, dict) else np.nan)

        df["dans_commission_competente"] = df["commissions"].fillna("").str.contains(
            _commission_attendue(cle), case=False, regex=True, na=False)

        morceaux.append(df)

    table = pd.concat(morceaux, ignore_index=True)
    # Intensité du lobbying déclaré sur le texte : constante au sein d'un texte,
    # elle ne sert qu'aux comparaisons entre textes (et jamais dans un modèle à
    # effets fixes de texte, où elle serait parfaitement colinéaire).
    intensite = (ciblage[ciblage["cible_texte"]].groupby("texte_cle")
                 .agg(nb_activites_lobby=("activite_id", "size"),
                      nb_organisations_lobby=("identifiant_national", "nunique")))
    table = table.merge(intensite, on="texte_cle", how="left")

    colonnes = [
        "texte_cle", "texte_libelle", "scrutin_uid", "numero_scrutin", "date_scrutin",
        "acteur_ref", "nom_complet", "civilite", "groupe", "groupe_abrev", "bloc",
        "region", "departement", "num_departement", "num_circo", "profession",
        "categorie_socpro", "premiere_election", "commissions",
        "dans_commission_competente", "position", "a_vote", "vote_pour",
        "position_majoritaire_groupe", "par_delegation",
        "nb_amendements_texte", "nb_amendements_adoptes_texte", "a_depose_amendement",
        "proximite_max", "proximite_top5", "lobby_le_plus_proche",
        "interet_sectoriel_declare", "nb_interets", "nb_declarations",
        "densite_hab_km2", "part_rurale",
        "nb_activites_lobby", "nb_organisations_lobby",
    ]
    table = table[[c for c in colonnes if c in table.columns]]
    logger.info("table d'analyse : %d lignes, %d députés, %d textes "
                "(%d votes exprimés)",
                len(table), table["acteur_ref"].nunique(), table["texte_cle"].nunique(),
                int(table["a_vote"].sum()))
    return table


#: Commission saisie au fond, par texte : sert la variable de contrôle
#: « le député siège-t-il dans la commission qui a examiné le texte ».
_COMMISSIONS = {
    "agriculture": "affaires économiques|développement durable",
    "defense": "défense",
    "fraudes": "finances|affaires sociales",
    "logement": "affaires économiques|développement durable",
}


def _commission_attendue(cle: str) -> str:
    return _COMMISSIONS.get(cle, "$^")


# --------------------------------------------------------------------------
# Table de dissidence (le niveau où il y a quelque chose à expliquer)
# --------------------------------------------------------------------------


def table_dissidence(*, scrutins: pd.DataFrame, votes: pd.DataFrame,
                     table_finale: pd.DataFrame,
                     textes: tuple[str, ...] | None = None) -> pd.DataFrame:
    """Une ligne par (député, scrutin d'amendement) sur les textes étudiés.

    Pourquoi cette table existe : sur le vote final, la discipline de groupe est
    quasi parfaite (voir le rapport), si bien qu'un modèle à effets fixes de
    groupe sépare parfaitement les données et n'identifie plus rien. L'influence
    marginale, s'il y en a une trace, se lit dans les **centaines de scrutins
    d'amendements** du même texte, où 3 à 5 % des votes s'écartent de la position
    majoritaire du groupe.

    Variable expliquée : ``dissident`` — le député vote autrement que la majorité
    de son groupe sur ce scrutin. Les caractéristiques individuelles sont
    reprises de la table des votes finaux, pour que les deux analyses portent
    exactement sur les mêmes variables.
    """
    cles = config.TEXTES_ANALYSE if textes is None else textes
    caracteristiques = table_finale.drop(columns=[
        c for c in ("scrutin_uid", "numero_scrutin", "date_scrutin", "position",
                    "a_vote", "vote_pour", "position_majoritaire_groupe",
                    "par_delegation") if c in table_finale.columns])

    morceaux = []
    for cle in cles:
        texte = config.TEXTES_PAR_CLE[cle]
        du_dossier = scrutins[scrutins["dossier_ref"] == texte.dossier_ref]
        # On exclut les votes sur l'ensemble : ils sont la variable expliquée de
        # l'autre table, et leur logique n'est pas celle d'un vote d'amendement.
        amendements_scr = du_dossier[~du_dossier["titre"].str.contains(
            r"l'ensemble (?:du|de la)", case=False, na=False, regex=True)]

        v = votes[votes["scrutin_uid"].isin(set(amendements_scr["scrutin_uid"]))].copy()
        v = v[v["position"].isin(["pour", "contre"])]
        v["dissident"] = (v["position"] != v["position_majoritaire_groupe"]).astype(int)
        v["texte_cle"] = cle
        v = v.merge(amendements_scr[["scrutin_uid", "numero", "date_scrutin", "sort"]],
                    on="scrutin_uid", how="left")
        v = v.merge(caracteristiques[caracteristiques["texte_cle"].eq(cle)],
                    on=["acteur_ref", "texte_cle"], how="inner")
        morceaux.append(v)

    table = pd.concat(morceaux, ignore_index=True)
    logger.info("table de dissidence : %d votes, %d députés, %d scrutins "
                "(taux de dissidence global %.2f %%)",
                len(table), table["acteur_ref"].nunique(), table["scrutin_uid"].nunique(),
                100 * table["dissident"].mean())
    return table

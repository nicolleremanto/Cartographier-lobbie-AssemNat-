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
                     *, seuil: float = 0.05, max_par_depute: int = 3) -> pd.DataFrame:
    """Arêtes « lobby ↔ député » du graphe biparti, pondérées par la proximité.

    On ne garde que les trois meilleures arêtes par député, au-dessus d'un
    seuil : un graphe complet de plusieurs centaines de nœuds n'apprend rien à
    personne. Le seuil de 0,05 est un choix de **lisibilité**, pas un test : il a
    été retenu parce qu'au-dessus (0,08) le graphe de la loi de programmation
    militaire tombait à une seule arête, et en dessous (0,03) celui de la loi
    agricole devenait illisible. La figure décrit, elle ne démontre pas — aucune
    conclusion du rapport n'en dépend.
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


def secteurs_lexique_du_texte(texte: config.TexteCible) -> list[str]:
    """Codes secteur du lexique d'intérêts correspondant à un texte."""
    return [code for code in texte.secteurs_hatvp if code in LEXIQUE_SECTEURS]


def table_analyse(*, scrutins: pd.DataFrame, votes: pd.DataFrame,
                  deputes_hatvp: pd.DataFrame, amendements: pd.DataFrame,
                  ciblage: pd.DataFrame, departements: pd.DataFrame,
                  profil_sectoriel: pd.DataFrame | None = None,
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
        # Deux mesures du même concept, gardées toutes les deux et comparées dans
        # le rapport : la première cherche le vocabulaire du texte dans les
        # libellés d'intérêts, la seconde passe par un classement sectoriel
        # explicite. Deux mesures bruitées qui concordent valent mieux qu'une
        # seule qu'on ne peut pas mettre à l'épreuve.
        df["interet_sectoriel_declare"] = matching.interet_sectoriel(df, texte)
        if profil_sectoriel is not None:
            codes = secteurs_lexique_du_texte(texte)
            presents = [c for c in codes if c in profil_sectoriel.columns]
            if presents:
                drapeau = (profil_sectoriel.set_index("acteur_ref")[presents].max(axis=1) > 0)
                df["interet_secteur_lexique"] = df["acteur_ref"].map(drapeau).fillna(False)
            else:
                df["interet_secteur_lexique"] = False
        else:
            df["interet_secteur_lexique"] = pd.NA

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
        "interet_sectoriel_declare", "interet_secteur_lexique",
        "nb_interets", "nb_declarations",
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


# --------------------------------------------------------------------------
# Niveau amendement : convergence lexicale et test placebo
# --------------------------------------------------------------------------


def _espace_tfidf(corpus: list[pd.Series]) -> TfidfVectorizer:
    """Apprend un espace TF-IDF commun à plusieurs corpus.

    Comparer deux corpus vectorisés séparément n'a pas de sens : les poids IDF
    diffèrent et les cosinus ne sont plus sur la même échelle. On apprend donc
    l'espace une fois, sur l'union.
    """
    vectoriseur = TfidfVectorizer(stop_words=MOTS_VIDES, ngram_range=(1, 2),
                                  min_df=2, max_df=0.8, sublinear_tf=True, norm="l2")
    vectoriseur.fit(pd.concat(corpus, ignore_index=True))
    return vectoriseur


def _objets_lobbies(ciblage: pd.DataFrame, cle: str) -> pd.DataFrame:
    """Objets déclarés de niveau 1 pour un texte, dédoublonnés."""
    objets = ciblage.loc[ciblage["texte_cle"].eq(cle) & ciblage["cible_nommee"],
                         ["activite_id", "denomination", "categorie_famille", "objet"]].copy()
    objets["document"] = objets["objet"].fillna("").map(normaliser)
    return objets[objets["document"].str.len() > 20].drop_duplicates("document")


def table_amendements(amendements: pd.DataFrame, ciblage: pd.DataFrame,
                      deputes_hatvp: pd.DataFrame,
                      textes: tuple[str, ...] | None = None,
                      *, min_caracteres: int = 150) -> pd.DataFrame:
    """Une ligne par amendement de député sur les textes étudiés.

    Deux variables de convergence lexicale sont calculées pour chaque amendement :

    ``proximite_lobby``    similarité avec les objets déclarés par les lobbies
                           ayant **nommé ce texte** ;
    ``proximite_placebo``  similarité avec les objets déclarés des lobbies d'un
                           **autre** texte de l'étude.

    La seconde est un test de falsification. Si la convergence mesurée captait
    seulement « cet amendement est rédigé dans un français administratif dense »,
    les deux variables auraient le même pouvoir explicatif. Si seule la première
    compte, la mesure capte bien quelque chose de sectoriel. C'est le garde-fou
    le moins coûteux contre la découverte d'un effet qui n'existe pas.
    """
    cles = config.TEXTES_ANALYSE if textes is None else textes
    # Permutation circulaire : chaque texte est testé contre le suivant.
    placebo = {cle: cles[(i + 1) % len(cles)] for i, cle in enumerate(cles)}

    morceaux = []
    for cle in cles:
        texte = config.TEXTES_PAR_CLE[cle]
        df = amendements[amendements["dossier_ref"].eq(texte.dossier_ref)
                         & amendements["type_auteur"].eq("Député")
                         & amendements["acteur_ref"].notna()].copy()
        if df.empty:
            logger.warning("[%s] aucun amendement de député", cle)
            continue

        df["document"] = (df["expose"].fillna("") + " " + df["dispositif"].fillna("")).map(normaliser)
        df["texte_exploitable"] = df["document"].str.len() >= min_caracteres

        objets_reels = _objets_lobbies(ciblage, cle)
        objets_placebo = _objets_lobbies(ciblage, placebo[cle])

        # Le maximum d'une similarité sur N documents croît mécaniquement avec N :
        # comparer 14 objets « défense » à 165 objets « fraudes » ferait gagner le
        # placebo sans aucune raison de fond. On ramène donc les deux corpus à la
        # même taille (tirage à graine fixe, donc reproductible).
        taille = min(len(objets_reels), len(objets_placebo))
        if taille:
            objets_reels = objets_reels.sample(taille, random_state=config.ALEA)
            objets_placebo = objets_placebo.sample(taille, random_state=config.ALEA)
        logger.info("[%s] corpus de comparaison ramenés à %d objets "
                    "(placebo : %s)", cle, taille, placebo[cle])

        corpus = [df["document"], objets_reels["document"], objets_placebo["document"]]
        if objets_reels.empty or objets_placebo.empty:
            logger.warning("[%s] corpus de lobbies vide, proximités laissées à 0", cle)
            df["proximite_lobby"] = 0.0
            df["proximite_placebo"] = 0.0
            df["lobby_le_plus_proche"] = None
        else:
            vectoriseur = _espace_tfidf([c for c in corpus if not c.empty])
            matrice = vectoriseur.transform(df["document"])
            sim_reel = (matrice @ vectoriseur.transform(objets_reels["document"]).T).toarray()
            sim_placebo = (matrice @ vectoriseur.transform(objets_placebo["document"]).T).toarray()
            df["proximite_lobby"] = sim_reel.max(axis=1)
            df["proximite_placebo"] = sim_placebo.max(axis=1)
            df["lobby_le_plus_proche"] = objets_reels["denomination"].to_numpy()[
                sim_reel.argmax(axis=1)]
        df.loc[~df["texte_exploitable"], ["proximite_lobby", "proximite_placebo"]] = np.nan

        df["texte_cle"] = cle
        df["texte_placebo"] = placebo[cle]
        morceaux.append(df)

    table = pd.concat(morceaux, ignore_index=True)
    table = table.merge(
        deputes_hatvp[["acteur_ref", "nom_complet", "groupe_abrev", "bloc", "departement",
                       "commissions", "interets_concat"]],
        on="acteur_ref", how="left")
    table["dans_commission_competente"] = [
        bool(pd.notna(com) and pd.Series([com]).str.contains(
            _commission_attendue(cle), case=False, regex=True).iloc[0])
        for com, cle in zip(table["commissions"], table["texte_cle"], strict=True)]
    table["sort_tranche"] = table["sort"].isin(["Adopté", "Rejeté"])
    table["log_cosignataires"] = np.log1p(table["nb_cosignataires"].fillna(0))

    colonnes = [
        "texte_cle", "texte_placebo", "amendement_uid", "numero_long", "dossier_ref",
        "acteur_ref", "nom_complet", "groupe_abrev", "bloc", "departement",
        "organe_examen", "article_vise", "article_additionnel", "nb_cosignataires",
        "log_cosignataires", "date_depot", "sort", "adopte", "sort_tranche",
        "texte_exploitable", "proximite_lobby", "proximite_placebo",
        "lobby_le_plus_proche", "dans_commission_competente",
    ]
    table = table[[c for c in colonnes if c in table.columns]]
    logger.info("table des amendements : %d lignes, %d auteurs, %d exploitables, "
                "taux d'adoption %.1f %% (sur %d amendements tranchés)",
                len(table), table["acteur_ref"].nunique(), int(table["texte_exploitable"].sum()),
                100 * table.loc[table["sort_tranche"], "adopte"].mean(),
                int(table["sort_tranche"].sum()))
    return table


# --------------------------------------------------------------------------
# Intérêts déclarés des députés : dédoublonnage et classement sectoriel
# --------------------------------------------------------------------------

#: Vocabulaire de rattachement d'un intérêt déclaré à un secteur HATVP. Ces
#: lexiques sont volontairement courts et lisibles : ils seront faux parfois, et
#: un lexique de trois pages le serait tout autant sans qu'on puisse le vérifier.
LEXIQUE_SECTEURS: dict[str, tuple[str, ...]] = {
    "AGRI": ("agricole", "agriculture", "exploitation agricole", "gaec", "earl",
             "viticole", "vignoble", "elevage", "cooperative agricole", "safer",
             "chambre d agriculture", "fnsea", "agroalimentaire", "cuma"),
    "SANTE": ("hopital", "clinique", "medecin", "pharmac", "infirmier", "chu",
              "sante", "medical", "ehpad", "laboratoire"),
    "FINANCE": ("banque", "assurance", "mutuelle", "credit", "caisse d epargne",
                "maif", "mgen", "macif", "groupama", "finance", "courtage"),
    "AMENAGEMENT": ("immobilier", "habitat", "hlm", "logement", "batiment",
                    "construction", "foncier", "amenagement", "urbanisme", "sci"),
    "EDUCATION": ("education nationale", "universite", "ecole", "college", "lycee",
                  "enseignant", "professeur", "formation", "cnrs"),
    "SECURITE": ("defense", "armee", "gendarmerie", "police", "thales", "dassault",
                 "naval group", "safran", "militaire"),
    "ENERGIE": ("energie", "edf", "engie", "petrol", "gaz", "nucleaire",
                "photovoltai", "eolien", "renouvelable"),
    "TRANSPORTS": ("sncf", "transport", "ratp", "logistique", "aerien", "portuaire",
                   "routier", "autoroute"),
    "NUMERIQUE": ("informatique", "numerique", "logiciel", "telecom", "orange",
                  "digital", "startup", "donnees"),
    "MEDIA": ("presse", "journal", "radio", "television", "media", "edition",
              "communication", "audiovisuel"),
    "JUSTICE": ("avocat", "notaire", "huissier", "barreau", "juridique", "greffe"),
    "PUBLIC": ("mairie", "commune", "departement", "region", "prefecture",
               "collectivite", "epci", "syndicat mixte", "ccas"),
}


def dedoublonner_interets(interets: pd.DataFrame) -> pd.DataFrame:
    """Supprime les répétitions dues aux déclarations modificatives.

    Un député qui dépose une déclaration initiale puis une modificative voit ses
    intérêts inchangés recopiés à l'identique. Les compter deux fois gonflerait
    mécaniquement les députés les plus actifs administrativement — exactement le
    contraire de ce qu'on cherche à mesurer.
    """
    if interets.empty:
        return interets
    avant = len(interets)
    propre = interets.drop_duplicates(
        subset=["nom_normalise", "rubrique", "libelle_normalise"]).reset_index(drop=True)
    logger.info("intérêts déclarés : %d lignes après dédoublonnage (%d doublons retirés, %.0f %%)",
                len(propre), avant - len(propre), 100 * (avant - len(propre)) / max(avant, 1))
    return propre


def classer_interets(interets: pd.DataFrame,
                     lexique: dict[str, tuple[str, ...]] | None = None) -> pd.DataFrame:
    """Associe à chaque intérêt déclaré zéro, un ou plusieurs secteurs.

    Un intérêt peut relever de deux secteurs (« mutuelle santé » est à la fois
    SANTE et FINANCE) : on garde les deux plutôt que d'arbitrer arbitrairement.
    """
    lexique = LEXIQUE_SECTEURS if lexique is None else lexique
    if interets.empty:
        return interets.assign(secteurs_interet="", n_secteurs=0)

    def _secteurs(libelle: str) -> str:
        trouves = [code for code, mots in lexique.items()
                   if any(mot in libelle for mot in mots)]
        return " | ".join(sorted(trouves))

    table = interets.copy()
    table["secteurs_interet"] = table["libelle_normalise"].fillna("").map(_secteurs)
    table["n_secteurs"] = table["secteurs_interet"].str.count(r"\|").add(1).where(
        table["secteurs_interet"].ne(""), 0)
    couverture = table["secteurs_interet"].ne("").mean()
    logger.info("classement sectoriel des intérêts : %.0f %% des libellés rattachés "
                "à au moins un secteur", 100 * couverture)
    return table


def profil_sectoriel_deputes(interets_classes: pd.DataFrame,
                             deputes: pd.DataFrame) -> pd.DataFrame:
    """Matrice député × secteur : le député déclare-t-il un intérêt dans ce secteur ?

    Les rubriques retenues excluent les mandats électifs, qui ne sont pas un
    intérêt privé : presque tous les députés ont été élus locaux, la variable
    serait constante et n'apprendrait rien.
    """
    rubriques_privees = {"activProfCinqDerniere", "activConsultant",
                         "participationDirigeant", "participationFinanciere",
                         "fonctionBenevole"}
    retenus = interets_classes[interets_classes["rubrique"].isin(rubriques_privees)
                               & interets_classes["secteurs_interet"].ne("")]
    paires = (retenus.assign(secteur=retenus["secteurs_interet"].str.split(" | ", regex=False))
              .explode("secteur")
              .loc[:, ["nom_normalise", "secteur"]]
              .drop_duplicates())
    matrice = (paires.assign(present=1)
               .pivot_table(index="nom_normalise", columns="secteur", values="present",
                            fill_value=0))
    profil = (deputes[["acteur_ref", "nom_complet", "nom_normalise", "groupe_abrev",
                       "bloc", "departement", "commissions"]]
              .merge(matrice, on="nom_normalise", how="left"))
    colonnes_secteurs = [c for c in matrice.columns]
    profil[colonnes_secteurs] = profil[colonnes_secteurs].fillna(0).astype(int)
    profil["n_secteurs_declares"] = profil[colonnes_secteurs].sum(axis=1)
    logger.info("profil sectoriel : %d députés, %d secteurs, "
                "%.0f %% déclarent au moins un intérêt privé classé",
                len(profil), len(colonnes_secteurs),
                100 * profil["n_secteurs_declares"].gt(0).mean())
    return profil


# --------------------------------------------------------------------------
# Déports : le seul lien nommé entre un député, un intérêt et un texte
# --------------------------------------------------------------------------


def table_deports(deports: pd.DataFrame, deputes: pd.DataFrame,
                  scrutins: pd.DataFrame, votes: pd.DataFrame,
                  *, legislature: str | None = None) -> pd.DataFrame:
    """Déports de la législature en cours, avec le comportement de vote observé.

    Un déport est une promesse : « je ne prendrai pas part au vote sur ce texte ».
    Comme les scrutins sont nominatifs, cette promesse est **vérifiable**. La
    table indique donc, pour chaque déport rattaché à un dossier, combien de fois
    le député a voté sur ce dossier et combien de fois il s'est effectivement
    abstenu ou n'a pas pris part au vote.

    L'effectif (neuf déports) interdit toute statistique. C'est une illustration,
    et un contrôle de cohérence du reste de la chaîne.
    """
    legislature = config.LEGISLATURE if legislature is None else legislature
    table = deports[deports["legislature"].eq(legislature)].copy()
    if table.empty:
        return table

    identites = deputes.set_index("acteur_ref")[["nom_complet", "groupe_abrev", "bloc"]]
    table = table.join(identites, on="acteur_ref")

    # Un déport qui ne vise que certains articles ne peut pas être vérifié au
    # niveau du dossier : le député a le droit de voter sur tout le reste du
    # texte. On ne conclut donc que sur les déports portant sur un texte entier.
    table["portee_texte_entier"] = ~table["type_cible"].fillna("").str.contains(
        "article", case=False)

    positions = []
    for _, ligne in table.iterrows():
        if pd.isna(ligne.get("dossier_ref")):
            positions.append({"n_scrutins_dossier": 0, "n_votes_exprimes": 0,
                              "n_abstentions_ou_absences": 0})
            continue
        # Seuls les scrutins **postérieurs** à la publication du déport sont
        # comparables : un déport ne vaut pas rétroactivement.
        du_dossier = scrutins[scrutins["dossier_ref"].eq(ligne["dossier_ref"])]
        if pd.notna(ligne.get("date_publication")):
            du_dossier = du_dossier[du_dossier["date_scrutin"] >= ligne["date_publication"]]
        du_dossier = du_dossier["scrutin_uid"]
        siens = votes[votes["scrutin_uid"].isin(set(du_dossier))
                      & votes["acteur_ref"].eq(ligne["acteur_ref"])]
        positions.append({
            "n_scrutins_dossier": int(len(du_dossier)),
            "n_votes_exprimes": int(siens["position"].isin(["pour", "contre"]).sum()),
            "n_abstentions_ou_absences": int(
                siens["position"].isin(["abstention", "non votant"]).sum()),
        })
    table = pd.concat([table.reset_index(drop=True),
                       pd.DataFrame(positions)], axis=1)
    table["part_sans_vote_exprime"] = (
        1 - table["n_votes_exprimes"] / table["n_scrutins_dossier"].replace(0, pd.NA))
    table["verifiable"] = (table["dossier_ref"].notna() & table["portee_texte_entier"]
                           & table["n_scrutins_dossier"].gt(0))
    table["deport_respecte"] = pd.NA
    table.loc[table["verifiable"], "deport_respecte"] = (
        table.loc[table["verifiable"], "n_votes_exprimes"] == 0)
    logger.info("déports de la législature %s : %d, dont %d rattachés à un dossier, "
                "%d vérifiables (portée = texte entier), %d respectés",
                legislature, len(table), int(table["dossier_ref"].notna().sum()),
                int(table["verifiable"].sum()),
                int(table.loc[table["verifiable"], "deport_respecte"].sum()))
    return table

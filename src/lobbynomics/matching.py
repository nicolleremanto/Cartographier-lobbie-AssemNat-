"""Étape 3 — rapprochement des bases. C'est ici que se joue le projet.

Deux rapprochements, de nature différente.

**A. Scrutin → dossier législatif (interne à l'Assemblée).**
Un scrutin sur deux ne porte pas de lien explicite vers son dossier : le champ
``objet.dossierLegislatif`` est nul, et le seul rattachement disponible est la
phrase du titre (« l'amendement n° 190 de M. Golliot après l'article 2 de la
proposition de loi visant à la nationalisation d'ArcelorMittal France… »). On
extrait la dénomination du texte de cette phrase, puis on la compare aux titres
de dossiers. Ce rapprochement est *vérifiable* : les 2 600 scrutins qui portent
déjà un lien explicite servent de jeu de test, et donnent une mesure honnête du
taux d'erreur de la méthode.

**B. Activité HATVP → texte de loi (entre bases).**
Là il n'y a aucune clé. Le répertoire ne contient ni numéro de texte, ni date
précise : un objet en texte libre, des domaines d'intervention, et une année
d'exercice. On combine donc quatre signaux faibles — secteur de l'organisation,
domaine d'intervention de l'activité, vocabulaire de l'objet, recouvrement
temporel avec la fenêtre de débat — et on ne retient que les activités portant
explicitement sur des « Lois ». Le résultat est une **présomption de ciblage**,
pas un fait : il est audité sur échantillon et le rapport en tire les
conséquences.
"""
from __future__ import annotations

import logging
import re

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

from . import config
from .parse_an import normaliser

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# A. Scrutin -> dossier législatif
# --------------------------------------------------------------------------

#: Amorces après lesquelles commence la dénomination du texte dans un titre de scrutin.
_AMORCES = (
    "du projet de loi constitutionnelle",
    "de la proposition de loi constitutionnelle",
    "du projet de loi organique",
    "de la proposition de loi organique",
    "du projet de loi",
    "de la proposition de loi",
    "de la proposition de resolution",
    "du projet de resolution",
)

#: Mentions de procédure à retirer en fin de titre.
_SUFFIXES = re.compile(
    r"\b(premiere|deuxieme|troisieme|nouvelle|seconde)\s+(lecture|deliberation)\b"
    r"|\blecture\s+definitive\b"
    r"|\bcommission\s+mixte\s+paritaire\b"
    r"|\btexte\s+de\s+la\s+commission\b"
)


def extraire_denomination(titre: str | None) -> str:
    """Isole la dénomination du texte de loi dans le titre d'un scrutin.

    >>> extraire_denomination("l'amendement n° 1 à l'article 4 de la proposition "
    ...                       "de loi visant à sortir la France du piège du narcotrafic "
    ...                       "(première lecture).")
    'visant a sortir la france du piege du narcotrafic'
    """
    base = normaliser(titre)
    if not base:
        return ""
    position = -1
    amorce_trouvee = ""
    for amorce in _AMORCES:
        p = base.find(amorce)
        # On garde l'amorce la plus tardive : « l'amendement … du projet de loi X »
        # place bien la dénomination après la dernière occurrence.
        if p >= 0 and (p > position or (p == position and len(amorce) > len(amorce_trouvee))):
            position, amorce_trouvee = p, amorce
    if position < 0:
        # Titres du type « l'ensemble du texte » : rien à extraire.
        return ""
    reste = base[position + len(amorce_trouvee):].strip()
    reste = _SUFFIXES.sub(" ", reste)
    reste = re.sub(r"\s+", " ", reste).strip(" .,;")
    return reste


def _cle_comparaison(titre_dossier: str) -> str:
    """Titre de dossier ramené à la même forme que la dénomination extraite."""
    base = normaliser(titre_dossier)
    for amorce in _AMORCES:
        if base.startswith(amorce):
            return base[len(amorce):].strip()
    return base


def rattacher_scrutins(scrutins: pd.DataFrame, dossiers: pd.DataFrame,
                       *, seuil: int | None = None, k: int = 12,
                       tolerance_score: float = 3.0) -> pd.DataFrame:
    """Ajoute à `scrutins` un ``dossier_ref`` résolu, sa source et son score.

    La similarité de titre seule ne suffit pas : l'Assemblée ouvre un dossier
    distinct par lecture et par chambre, si bien que plusieurs dossiers portent
    **exactement** le même titre (« Nationalisation d'ArcelorMittal France »
    existe deux fois). Un score de 100 est alors ambigu. On garde donc les `k`
    meilleurs candidats, on conserve ceux à moins de `tolerance_score` points du
    meilleur, puis on tranche par la date : le dossier retenu est celui dont la
    fenêtre d'activité parlementaire est la plus proche de la date du scrutin.

    Colonnes ajoutées :

    ``denomination``     dénomination extraite du titre (vide si inextractible)
    ``dossier_ref``      dossier retenu, explicite si disponible, sinon inféré
    ``origine_lien``     ``declare`` | ``fuzzy`` | ``aucun``
    ``score_fuzzy``      score rapidfuzz du meilleur candidat (0-100)
    ``dossier_fuzzy``    candidat fuzzy, calculé même quand un lien déclaré existe
                         (c'est ce qui permet d'évaluer la méthode)
    ``n_candidats_ex_aequo``  nombre de dossiers à égalité de score
    """
    seuil = config.SEUIL_FUZZY_SCRUTIN if seuil is None else seuil
    scrutins = scrutins.copy()
    scrutins["denomination"] = scrutins["titre"].map(extraire_denomination)

    candidats = dossiers.dropna(subset=["titre"]).copy()
    candidats["cle"] = candidats["titre"].map(_cle_comparaison)
    candidats = candidats[candidats["cle"].str.len() > 10].reset_index(drop=True)
    choix = candidats["cle"].tolist()
    refs = candidats["dossier_ref"].tolist()
    debuts = pd.to_datetime(candidats["date_premier_acte"]).tolist()
    fins = pd.to_datetime(candidats["date_dernier_acte"]).tolist()

    # Une dénomination revient des centaines de fois (un texte = des centaines de
    # scrutins) : on ne calcule les scores qu'une fois par dénomination distincte.
    uniques = sorted({d for d in scrutins["denomination"] if len(d) > 10})
    logger.info("rattachement de %d dénominations distinctes à %d dossiers",
                len(uniques), len(choix))

    candidats_par_denom: dict[str, list[tuple[int, float]]] = {}
    for denomination in uniques:
        trouves = process.extract(denomination, choix, scorer=fuzz.token_set_ratio,
                                  limit=k, score_cutoff=50)
        if not trouves:
            candidats_par_denom[denomination] = []
            continue
        meilleur_score = trouves[0][1]
        candidats_par_denom[denomination] = [
            (index, float(score)) for _, score, index in trouves
            if meilleur_score - score <= tolerance_score
        ]

    def _ecart_jours(index: int, date_scrutin: pd.Timestamp) -> float:
        """Distance en jours entre un scrutin et la fenêtre d'activité d'un dossier."""
        debut, fin = debuts[index], fins[index]
        if pd.isna(debut) and pd.isna(fin):
            return 1e9
        debut = fin if pd.isna(debut) else debut
        fin = debut if pd.isna(fin) else fin
        if debut <= date_scrutin <= fin:
            return 0.0
        return min(abs((date_scrutin - debut).days), abs((date_scrutin - fin).days))

    dates = pd.to_datetime(scrutins["date_scrutin"], errors="coerce")
    retenus_ref, retenus_score, ex_aequo = [], [], []
    for denomination, date_scrutin in zip(scrutins["denomination"], dates, strict=True):
        liste = candidats_par_denom.get(denomination, [])
        if not liste:
            retenus_ref.append(None); retenus_score.append(0.0); ex_aequo.append(0)
            continue
        if pd.isna(date_scrutin) or len(liste) == 1:
            index, score = liste[0]
        else:
            index, score = min(liste, key=lambda c: (_ecart_jours(c[0], date_scrutin), -c[1]))
        retenus_ref.append(refs[index]); retenus_score.append(score); ex_aequo.append(len(liste))

    scrutins["dossier_fuzzy"] = retenus_ref
    scrutins["score_fuzzy"] = retenus_score
    scrutins["n_candidats_ex_aequo"] = ex_aequo

    retenu = scrutins["dossier_fuzzy"].where(scrutins["score_fuzzy"] >= seuil)
    scrutins["dossier_ref"] = (scrutins["dossier_ref_declare"]
                               .astype("object").fillna(retenu.astype("object")))
    scrutins["origine_lien"] = "aucun"
    scrutins.loc[scrutins["dossier_ref_declare"].notna(), "origine_lien"] = "declare"
    scrutins.loc[scrutins["dossier_ref_declare"].isna()
                 & scrutins["dossier_ref"].notna(), "origine_lien"] = "fuzzy"

    logger.info("scrutins rattachés : %s",
                scrutins["origine_lien"].value_counts().to_dict())
    logger.info("dénominations à candidats multiples ex aequo : %d sur %d",
                sum(1 for d in uniques if len(candidats_par_denom.get(d, [])) > 1), len(uniques))
    return scrutins


def evaluer_rattachement(scrutins: pd.DataFrame) -> pd.DataFrame:
    """Mesure la qualité du rattachement fuzzy sur les scrutins à lien déclaré.

    Les scrutins qui portent un ``dossierRef`` explicite constituent une vérité
    terrain gratuite : on y applique quand même la méthode fuzzy et on compare.
    On balaie plusieurs seuils pour justifier celui retenu dans `config`.
    """
    test = scrutins[scrutins["dossier_ref_declare"].notna()
                    & (scrutins["denomination"].str.len() > 10)].copy()
    test["correct"] = test["dossier_fuzzy"] == test["dossier_ref_declare"]

    lignes = []
    for seuil in range(60, 101, 5):
        retenus = test[test["score_fuzzy"] >= seuil]
        lignes.append({
            "seuil": seuil,
            "n_test": len(test),
            "n_retenus": len(retenus),
            "couverture": len(retenus) / len(test) if len(test) else float("nan"),
            "precision": retenus["correct"].mean() if len(retenus) else float("nan"),
        })
    rapport = pd.DataFrame(lignes)
    logger.info("évaluation du rattachement fuzzy (n=%d scrutins à lien déclaré)", len(test))
    return rapport


# --------------------------------------------------------------------------
# B. Activité HATVP -> texte de loi ciblé
# --------------------------------------------------------------------------


def fenetre_debat(dossiers: pd.DataFrame, texte: config.TexteCible,
                  *, marge_mois: int | None = None) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Fenêtre temporelle du débat parlementaire, élargie d'une marge.

    La marge est nécessaire parce que le lobbying précède le dépôt du texte : on
    cherche les activités déclarées *autour* du débat, pas seulement pendant.
    """
    marge = config.MARGE_FENETRE_MOIS if marge_mois is None else marge_mois
    ligne = dossiers.loc[dossiers["dossier_ref"] == texte.dossier_ref]
    if ligne.empty:
        raise KeyError(f"dossier {texte.dossier_ref} absent de la table des dossiers")
    ligne = ligne.iloc[0]
    debut = pd.to_datetime(ligne["date_premier_acte"])
    fin = pd.to_datetime(ligne["date_dernier_acte"])
    return (debut - pd.DateOffset(months=marge), fin + pd.DateOffset(months=marge))


def _compte_mots_cles(objet_normalise: str, mots_cles: tuple[str, ...]) -> int:
    return sum(1 for mot in mots_cles if mot in objet_normalise)


def nomme_le_texte(objet_normalise: str, texte: config.TexteCible) -> bool:
    """L'objet déclaré désigne-t-il explicitement ce texte de loi ?

    Deux façons de nommer un texte dans le répertoire : l'intitulé officiel, ou
    l'une des abréviations d'usage (« LPM », « PJL fraude », « loi d'urgence
    agricole »). On teste donc l'intitulé normalisé et la liste d'alias **en
    sous-chaîne exacte**.

    Pourquoi pas de similarité floue ici : les objets déclarés sont des phrases
    entières, et un score partiel de type ``partial_token_set_ratio`` renvoie
    100 dès que les mots du titre apparaissent n'importe où, même dispersés —
    testé, il retenait 11 000 activités sur 11 500, dont des déclarations sur
    le PLFSS. Le flou est utile pour comparer *deux titres* (c'est le cas du
    rattachement des scrutins) ; il est hors sujet pour chercher un titre dans
    un paragraphe. Le prix de ce choix est un rappel faible, assumé et mesuré.
    """
    if not objet_normalise:
        return False
    if normaliser(texte.libelle) in objet_normalise:
        return True
    return any(alias in objet_normalise for alias in texte.alias)


def fenetre_debat(dossiers: pd.DataFrame, texte: config.TexteCible,
                  *, marge_mois: int | None = None) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Fenêtre temporelle du débat parlementaire, élargie d'une marge.

    La marge est nécessaire parce que le lobbying précède le dépôt du texte : on
    cherche les activités déclarées *autour* du débat, pas seulement pendant.
    """
    marge = config.MARGE_FENETRE_MOIS if marge_mois is None else marge_mois
    ligne = dossiers.loc[dossiers["dossier_ref"] == texte.dossier_ref]
    if ligne.empty:
        raise KeyError(f"dossier {texte.dossier_ref} absent de la table des dossiers")
    ligne = ligne.iloc[0]
    debut = pd.to_datetime(ligne["date_premier_acte"])
    fin = pd.to_datetime(ligne["date_dernier_acte"])
    return (debut - pd.DateOffset(months=marge), fin + pd.DateOffset(months=marge))


def _compte_mots_cles(objet_normalise: str, mots_cles: tuple[str, ...]) -> int:
    return sum(1 for mot in mots_cles if mot in objet_normalise)



def score_activites(activites: pd.DataFrame, dossiers: pd.DataFrame,
                    texte: config.TexteCible) -> pd.DataFrame:
    """Score chaque activité HATVP au regard d'un texte de loi.

    Quatre signaux, volontairement séparés pour rester interprétables :

    ``sect_ok``  l'organisation déclare au moins un secteur d'activité du texte
    ``dom_ok``   l'activité déclare au moins un domaine d'intervention du texte
    ``n_mots``   nombre de mots-clés du texte présents dans l'objet déclaré
    ``fuzzy``    similarité de l'objet déclaré avec le titre du dossier

    Le filtre dur : l'activité doit porter sur des « Lois » et son exercice doit
    recouvrir la fenêtre de débat. Sans ces deux conditions, le rapprochement
    n'a aucun sens.
    """
    debut, fin = fenetre_debat(dossiers, texte)
    titre_norm = normaliser(
        dossiers.loc[dossiers["dossier_ref"] == texte.dossier_ref, "titre"].iloc[0])

    df = activites.copy()
    ex_debut = pd.to_datetime(df["exercice_debut"], errors="coerce")
    ex_fin = pd.to_datetime(df["exercice_fin"], errors="coerce")
    df["dans_fenetre"] = (ex_fin >= debut) & (ex_debut <= fin)

    secteurs = set(texte.secteurs_hatvp)
    df["sect_ok"] = df["secteurs"].fillna("").map(
        lambda s: bool(secteurs & {x.strip() for x in s.split("|")}))
    domaines = {normaliser(d) for d in texte.domaines_hatvp}
    df["dom_ok"] = df["domaines"].fillna("").map(
        lambda s: bool(domaines & {normaliser(x) for x in s.split("|")}))
    df["n_mots"] = df["objet_normalise"].fillna("").map(
        lambda o: _compte_mots_cles(o, texte.mots_cles))
    df["fuzzy"] = df["objet_normalise"].fillna("").map(
        lambda o: fuzz.token_set_ratio(o, titre_norm) if o else 0.0)

    # Score composite, borné à 100, pensé pour être lisible plutôt que optimal :
    # le vocabulaire explicite pèse plus que l'appartenance sectorielle, qui est
    # déclarée une fois pour toute l'organisation et donc très large.
    df["score"] = (
        35 * df["n_mots"].clip(upper=3) / 3
        + 25 * df["dom_ok"]
        + 15 * df["sect_ok"]
        + 25 * (df["fuzzy"] / 100)
    ).round(1)

    df["eligible"] = df["dans_fenetre"] & df["cible_loi"]

    # Niveau 1 — le texte est nommé. Règle étroite et vérifiable : c'est elle
    # qui sert de variable d'exposition dans l'analyse.
    df["nomme_texte"] = df["objet_normalise"].fillna("").map(
        lambda o: nomme_le_texte(o, texte))
    df["cible_nommee"] = df["eligible"] & df["nomme_texte"]

    # Niveau 2 — simple voisinage thématique. Beaucoup plus large, et l'audit
    # manuel montre qu'il est majoritairement faux si on le lit comme « cette
    # organisation a travaillé sur ce texte ». On le conserve pour décrire
    # l'écosystème sectoriel autour d'un texte, jamais comme preuve de ciblage.
    df["cible_thematique"] = (
        df["eligible"]
        & (df["n_mots"] >= 1)
        & (df["dom_ok"] | df["sect_ok"])
        & (df["score"] >= config.SEUIL_FUZZY_ACTIVITE * 0.6)
    )
    df["cible_texte"] = df["cible_nommee"]      # la définition retenue par défaut
    df["niveau_ciblage"] = np.where(
        df["cible_nommee"], "1 - texte nommé",
        np.where(df["cible_thematique"], "2 - voisinage thématique", "0 - écarté"))
    df["texte_cle"] = texte.cle
    logger.info(
        "[%s] fenêtre %s → %s | %d activités éligibles | niveau 1 (texte nommé) : "
        "%d activités, %d organisations | niveau 2 (thématique) : %d activités",
        texte.cle, debut.date(), fin.date(), int(df["eligible"].sum()),
        int(df["cible_nommee"].sum()),
        df.loc[df["cible_nommee"], "identifiant_national"].nunique(),
        int(df["cible_thematique"].sum()))
    return df


COLONNES_CIBLAGE = [
    "texte_cle", "activite_id", "identifiant_national", "denomination",
    "categorie_famille", "secteurs", "domaines", "objet", "exercice_annee",
    "exercice_debut", "exercice_fin", "responsables_publics", "decisions_concernees",
    "actions_menees", "montant_depense", "sect_ok", "dom_ok", "n_mots", "fuzzy",
    "score", "dans_fenetre", "eligible", "nomme_texte", "cible_nommee",
    "cible_thematique", "cible_texte", "niveau_ciblage",
]


def precision_par_niveau(audit: pd.DataFrame) -> pd.DataFrame:
    """Taux de vrais ciblages par niveau, lu directement sur l'audit annoté."""
    annote = audit[audit["verdict_manuel"].isin(["oui", "non", "incertain"])]
    if annote.empty:
        return pd.DataFrame()
    table = (annote.assign(vrai=annote["verdict_manuel"].eq("oui"),
                           incertain=annote["verdict_manuel"].eq("incertain"))
             .groupby("niveau_ciblage")
             .agg(n_annote=("vrai", "size"), n_vrais=("vrai", "sum"),
                  n_incertains=("incertain", "sum")))
    table["precision"] = table["n_vrais"] / (table["n_annote"] - table["n_incertains"])
    return table.round(3)


def table_ciblage(activites: pd.DataFrame, dossiers: pd.DataFrame,
                  textes: tuple[config.TexteCible, ...] | None = None) -> pd.DataFrame:
    """Empile les scores de ciblage pour tous les textes étudiés."""
    textes = config.TEXTES_CIBLES if textes is None else textes
    morceaux = [score_activites(activites, dossiers, t)[COLONNES_CIBLAGE] for t in textes]
    complet = pd.concat(morceaux, ignore_index=True)

    # On ne conserve que les paires éligibles (activité portant sur une loi, et
    # exercice recouvrant la fenêtre de débat). Le produit cartésien complet fait
    # 452 000 lignes et 42 Mo pour aucune information supplémentaire : toutes les
    # étapes en aval travaillent sur le sous-ensemble éligible, et un dépôt Git
    # n'est pas un espace de stockage.
    ciblage = complet[complet["eligible"]].reset_index(drop=True)
    logger.info("table de ciblage : %d paires éligibles conservées sur %d évaluées "
                "— niveau 1 : %d, niveau 2 : %d",
                len(ciblage), len(complet), int(ciblage["cible_nommee"].sum()),
                int(ciblage["cible_thematique"].sum()))
    return ciblage


def echantillon_audit(ciblage: pd.DataFrame, *, taille: int | None = None,
                      graine: int | None = None) -> pd.DataFrame:
    """Échantillon stratifié à relire à la main pour estimer le taux d'erreur.

    On tire *autant* de paires retenues que de paires rejetées mais proches du
    seuil : relire seulement les retenues mesurerait la précision sans rien dire
    des rappels manqués.
    """
    taille = config.TAILLE_ECHANTILLON_AUDIT if taille is None else taille
    graine = config.ALEA if graine is None else graine
    eligibles = ciblage[ciblage["eligible"]]
    niveau1 = eligibles[eligibles["cible_nommee"]]
    niveau2 = eligibles[eligibles["cible_thematique"] & ~eligibles["cible_nommee"]]
    ecartees = eligibles[~eligibles["cible_thematique"] & ~eligibles["cible_nommee"]
                         & (eligibles["score"] >= 25)]

    tiers = max(taille // 3, 1)
    tirage = pd.concat([
        niveau1.sample(min(tiers, len(niveau1)), random_state=graine),
        niveau2.sample(min(tiers, len(niveau2)), random_state=graine),
        ecartees.sample(min(taille - 2 * tiers, len(ecartees)), random_state=graine),
    ])
    tirage = tirage.sample(frac=1, random_state=graine).reset_index(drop=True)
    tirage["verdict_manuel"] = ""   # à remplir : oui / non / incertain
    tirage["commentaire"] = ""
    logger.info("échantillon d'audit : %d paires — %s",
                len(tirage), tirage["niveau_ciblage"].value_counts().to_dict())
    return tirage


def taux_erreur(audit: pd.DataFrame, *, colonne: str = "cible_texte") -> dict[str, float]:
    """Précision, rappel et F1 du ciblage, à partir d'un audit annoté.

    Les paires annotées « incertain » sont écartées du calcul et comptées à
    part : les inclure d'un côté ou de l'autre fabriquerait le résultat.
    """
    annote = audit[audit["verdict_manuel"].isin(["oui", "non"])].copy()
    if annote.empty:
        return {"n_annote": 0}
    annote["cible_texte"] = annote[colonne]
    annote["vrai"] = annote["verdict_manuel"].eq("oui")
    vp = int((annote["cible_texte"] & annote["vrai"]).sum())
    fp = int((annote["cible_texte"] & ~annote["vrai"]).sum())
    fn = int((~annote["cible_texte"] & annote["vrai"]).sum())
    vn = int((~annote["cible_texte"] & ~annote["vrai"]).sum())
    precision = vp / (vp + fp) if vp + fp else float("nan")
    rappel = vp / (vp + fn) if vp + fn else float("nan")
    return {
        "n_annote": len(annote),
        "n_incertain": int(audit["verdict_manuel"].eq("incertain").sum()),
        "vp": vp, "fp": fp, "fn": fn, "vn": vn,
        "precision": precision, "rappel": rappel,
        "f1": 2 * precision * rappel / (precision + rappel)
        if precision + rappel else float("nan"),
    }


# --------------------------------------------------------------------------
# C. Députés <-> HATVP (jointure propre, pour mémoire)
# --------------------------------------------------------------------------


def rattacher_deputes_hatvp(deputes: pd.DataFrame, index_declarations: pd.DataFrame,
                            interets: pd.DataFrame) -> pd.DataFrame:
    """Relie chaque député à ses déclarations HATVP.

    Deux clés, dans cet ordre :

    1. ``uri_hatvp`` — l'Assemblée publie l'URL de la fiche HATVP de chaque
       député. C'est une clé exacte, fournie par la source : aucune raison de
       faire du fuzzy ici, et c'est le contre-exemple utile dans le rapport.
    2. le nom normalisé, uniquement pour rattacher le *contenu* des déclarations
       (`declarations.xml` ne porte pas l'URL de la fiche).
    """
    uris = (index_declarations.groupby("uri_hatvp")
            .agg(nb_declarations=("type_document", "size"),
                 types_declarations=("type_document", lambda s: " | ".join(sorted(set(s)))),
                 derniere_declaration=("date_depot", "max"))
            .reset_index())
    fusion = deputes.merge(uris, on="uri_hatvp", how="left")
    taux = fusion["nb_declarations"].notna().mean()
    logger.info("jointure exacte députés ↔ fiches HATVP par uri_hatvp : %.1f %% appariés",
                100 * taux)

    if not interets.empty:
        par_nom = (interets.groupby("nom_normalise")
                   .agg(nb_interets=("libelle", "size"),
                        interets_concat=("libelle_normalise", lambda s: " ; ".join(s)))
                   .reset_index())
        fusion = fusion.merge(par_nom, on="nom_normalise", how="left")
        fusion["nb_interets"] = fusion["nb_interets"].fillna(0).astype(int)
        fusion["interets_concat"] = fusion["interets_concat"].fillna("")
        logger.info("jointure par nom normalisé ↔ contenu des déclarations : %.1f %% appariés",
                    100 * fusion["nb_interets"].gt(0).mean())
    return fusion


def interet_sectoriel(fusion: pd.DataFrame, texte: config.TexteCible) -> pd.Series:
    """Le député déclare-t-il un intérêt dans le secteur du texte ?

    Mesure volontairement grossière (vocabulaire du texte cherché dans les
    libellés d'intérêts déclarés) et donc à prendre comme un indicateur bruité ;
    elle sert de contrôle individuel, pas de preuve.
    """
    concat = fusion.get("interets_concat", pd.Series("", index=fusion.index)).fillna("")
    return concat.map(lambda s: _compte_mots_cles(s, texte.mots_cles) > 0)

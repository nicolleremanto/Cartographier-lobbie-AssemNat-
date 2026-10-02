"""Étape 6 — figures du rapport.

Un principe : une figure par question, titrée par sa réponse. Toutes les
fonctions prennent un `DataFrame` et rendent une `Figure` matplotlib ; l'écriture
sur disque est faite par `enregistrer`, ce qui permet de les appeler depuis le
notebook sans effet de bord.
"""
from __future__ import annotations

import logging
import textwrap

import matplotlib as mpl
import matplotlib.patheffects as patheffects
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd

from . import config

logger = logging.getLogger(__name__)

# Palette sobre, lisible en noir et blanc, et ordre politique conventionnel
# (de la gauche vers la droite) pour que les graphiques se lisent sans légende.
ORDRE_BLOCS = ["gauche radicale", "gauche", "centre", "droite", "droite radicale",
               "non inscrit", "autre"]
COULEURS_BLOCS = {
    "gauche radicale": "#8e1d2b", "gauche": "#d4504f", "centre": "#d9a13b",
    "droite": "#3f6fa8", "droite radicale": "#1f3b63", "non inscrit": "#8c8c8c",
    "autre": "#bfbfbf",
}
COULEURS_TEXTES = {"agriculture": "#4c8c4a", "defense": "#4a6c8c",
                   "fraudes": "#8c6a4a", "logement": "#6a4a8c"}

#: Noms de variables lisibles, pour que les figures se passent du code source.
ETIQUETTES_VARIABLES = {
    "proximite_max_std": "proximité lexicale avec les lobbies (+1 écart-type)",
    "proximite_top5": "proximité lexicale moyenne (5 plus proches)",
    "interet_sectoriel_declare": "intérêt déclaré dans le secteur du texte",
    "part_rurale_std": "ruralité de la circonscription (+1 écart-type)",
    "dans_commission_competente": "membre de la commission saisie au fond",
    "a_depose_amendement": "a déposé un amendement sur le texte",
    "log_amendements": "nombre d'amendements déposés (log)",
    "proximite_lobby_std": "proximité aux lobbies du texte (+1 écart-type)",
    "proximite_placebo_std": "proximité aux lobbies d'un autre texte — témoin",
    "log_cosignataires": "nombre de cosignataires (log)",
    "article_additionnel": "article additionnel",
    "interet_secteur_lexique": "intérêt déclaré dans le secteur (classement sectoriel)",
    "bloc": "bloc", "texte_cle": "texte",
}


def _etiquette(nom: str) -> str:
    """Rend lisible un nom de terme de régression (`C(bloc)[T.centre]` → `bloc : centre`)."""
    propre = nom.replace("C(", "").replace(")[T.", " : ").replace("]", "")
    if " : " in propre:
        facteur, modalite = propre.split(" : ", 1)
        return f"{ETIQUETTES_VARIABLES.get(facteur, facteur)} : {modalite}"
    return ETIQUETTES_VARIABLES.get(propre, propre)


def style():
    """Applique le style du rapport. Appelé une fois en tête de notebook."""
    mpl.rcParams.update({
        "figure.dpi": 110, "savefig.dpi": 160, "savefig.bbox": "tight",
        "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.alpha": 0.25, "grid.linestyle": ":",
        "figure.facecolor": "white", "axes.facecolor": "white",
        "legend.frameon": False,
    })


def enregistrer(figure: plt.Figure, nom: str) -> str:
    """Écrit une figure dans `reports/figures/` et retourne son chemin."""
    chemin = config.FIGURES / f"{nom}.png"
    figure.savefig(chemin)
    logger.info("figure écrite : %s", chemin.name)
    return str(chemin)


def _ordonner(series_index: pd.Index) -> list[str]:
    return [b for b in ORDRE_BLOCS if b in set(series_index)]


def _etiquettes_blocs(blocs) -> list[str]:
    """Noms de blocs repliés sur deux lignes : « droite radicale » déborde sinon."""
    return [textwrap.fill(str(b), 9) for b in blocs]


def _habiller(ax, titre: str, sous_titre: str = "", source: str = ""):
    """Titre (= la conclusion de la figure), sous-titre (= ce qui est mesuré), source."""
    ax.set_title(titre, loc="left", pad=26 if sous_titre else 10)
    if sous_titre:
        ax.text(0, 1.015, textwrap.fill(sous_titre, 100), transform=ax.transAxes,
                fontsize=9, color="#555555", va="bottom")
    if source:
        ax.annotate(textwrap.fill(source, 115), xy=(0, 0), xycoords="axes fraction",
                    xytext=(0, -42), textcoords="offset points",
                    fontsize=7.5, color="#777777", va="top")


# --------------------------------------------------------------------------
# 1. Qualité du rapprochement des bases
# --------------------------------------------------------------------------


def figure_qualite_matching(rapport: pd.DataFrame) -> plt.Figure:
    """Couverture et précision du rattachement scrutin → dossier, selon le seuil."""
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(rapport["seuil"], 100 * rapport["precision"], marker="o",
            color="#1f3b63", label="précision")
    ax.plot(rapport["seuil"], 100 * rapport["couverture"], marker="s",
            color="#d4504f", label="couverture")
    ax.axvline(config.SEUIL_FUZZY_SCRUTIN, color="#444444", ls="--", lw=1)
    ax.annotate(f"seuil retenu : {config.SEUIL_FUZZY_SCRUTIN}",
                xy=(config.SEUIL_FUZZY_SCRUTIN, 55), xytext=(5, 0),
                textcoords="offset points", fontsize=8.5, color="#444444")
    ax.set_xlabel("seuil de similarité rapidfuzz (token_set_ratio)")
    ax.set_ylabel("%")
    ax.set_ylim(50, 102)
    ax.legend(loc="lower left")
    _habiller(ax,
              "Au-delà de 80, le rattachement devient fiable au prix d'un sixième des scrutins",
              f"validation sur les {int(rapport['n_test'].iloc[0])} scrutins qui portent "
              "déjà un lien explicite vers leur dossier",
              "Source : open data Assemblée nationale, XVIIe législature.")
    return fig


# --------------------------------------------------------------------------
# 2. Intensité et structure du lobbying déclaré
# --------------------------------------------------------------------------


def figure_intensite_lobbying(ciblage: pd.DataFrame) -> plt.Figure:
    """Ce que chaque niveau de ciblage retient, texte par texte.

    Deux barres par texte, en échelle log : le niveau 1 (le texte est nommé dans
    l'objet déclaré) est deux ordres de grandeur plus petit que le niveau 2
    (simple voisinage thématique). L'écart est le message de la figure.
    """
    agr = (ciblage.groupby("texte_cle")
           .agg(niveau1=("cible_nommee", "sum"), niveau2=("cible_thematique", "sum"))
           .reindex([t.cle for t in config.TEXTES_CIBLES]).fillna(0))

    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    x = np.arange(len(agr))
    ax.bar(x - 0.2, agr["niveau2"], width=0.4, color="#c9c0a8",
           label="niveau 2 — voisinage thématique")
    ax.bar(x + 0.2, agr["niveau1"], width=0.4, color="#1f3b63",
           label="niveau 1 — le texte est nommé")
    for i, (n2, n1) in enumerate(zip(agr["niveau2"], agr["niveau1"], strict=True)):
        ax.text(i - 0.2, max(n2, 0.6), f"{int(n2)}", ha="center", va="bottom", fontsize=8.5)
        ax.text(i + 0.2, max(n1, 0.6), f"{int(n1)}", ha="center", va="bottom", fontsize=8.5)
    ax.set_yscale("symlog", linthresh=1)
    ax.set_ylabel("activités déclarées retenues (échelle log)")
    ax.set_xticks(x, agr.index)
    ax.legend()
    _habiller(ax, "Exiger que le texte soit nommé divise le volume retenu par vingt à cinquante",
              "activités du répertoire HATVP retenues par chacun des deux niveaux de ciblage",
              "Sources : répertoire HATVP des représentants d'intérêts × dossiers législatifs AN. "
              "Le texte « logement » n'est nommé par aucune activité : il sert de cas témoin.")
    return fig


def figure_top_organisations(ciblage: pd.DataFrame, texte_cle: str,
                             n: int = 12) -> plt.Figure:
    """Organisations les plus présentes sur un texte, colorées par famille."""
    retenues = ciblage[(ciblage["texte_cle"] == texte_cle)
                       & (ciblage["cible_nommee"] | ciblage["cible_thematique"])]
    top = (retenues.groupby(["denomination", "categorie_famille"])
           .size().sort_values(ascending=False).head(n).reset_index(name="activites"))
    familles = sorted(top["categorie_famille"].fillna("non renseignée").unique())
    palette = dict(zip(familles, plt.cm.tab10.colors, strict=False))

    fig, ax = plt.subplots(figsize=(8, 0.42 * len(top) + 1.8))
    etiquettes = [textwrap.shorten(d.title(), 46, placeholder="…") for d in top["denomination"]]
    ax.barh(etiquettes[::-1], top["activites"][::-1],
            color=[palette.get(f or "non renseignée", "#999999")
                   for f in top["categorie_famille"][::-1]])
    ax.set_xlabel("nombre d'activités déclarées retenues")
    ax.grid(axis="y", visible=False)
    poignees = [plt.Rectangle((0, 0), 1, 1, color=palette[f]) for f in familles]
    ax.legend(poignees, familles, fontsize=8, loc="lower right")
    texte = config.TEXTES_PAR_CLE[texte_cle]
    _habiller(ax, f"Qui gravite autour du texte « {texte_cle} »",
              textwrap.shorten(texte.libelle, 95, placeholder="…"),
              "Source : répertoire HATVP. Une « activité » est une déclaration de l'organisation, "
              "non une preuve de contact avec un député.")
    return fig


def figure_secteurs_textes(ciblage: pd.DataFrame) -> plt.Figure:
    """Carte de chaleur : familles d'organisations × textes."""
    retenues = ciblage[ciblage["cible_nommee"] | ciblage["cible_thematique"]].copy()
    retenues["categorie_famille"] = retenues["categorie_famille"].fillna("non renseignée")
    croise = pd.crosstab(retenues["categorie_famille"], retenues["texte_cle"],
                         normalize="columns") * 100
    croise = croise.reindex(columns=[t.cle for t in config.TEXTES_CIBLES
                                     if t.cle in croise.columns])

    fig, ax = plt.subplots(figsize=(1.6 * len(croise.columns) + 3.5, 0.45 * len(croise) + 2))
    image = ax.imshow(croise.to_numpy(), cmap="YlGnBu", aspect="auto")
    ax.set_xticks(range(len(croise.columns)), croise.columns)
    ax.set_yticks(range(len(croise.index)), croise.index, fontsize=9)
    for i in range(croise.shape[0]):
        for j in range(croise.shape[1]):
            valeur = croise.iat[i, j]
            if valeur >= 1:
                ax.text(j, i, f"{valeur:.0f}", ha="center", va="center", fontsize=8,
                        color="white" if valeur > croise.to_numpy().max() / 2 else "#222222")
    ax.grid(visible=False)
    fig.colorbar(image, ax=ax, label="% des activités du texte", shrink=0.8)
    _habiller(ax, "Chaque texte attire une population d'acteurs différente",
              "répartition des activités retenues par famille d'organisation",
              "Source : répertoire HATVP, catégorie déclarée par l'organisation.")
    return fig


# --------------------------------------------------------------------------
# 3. Votes
# --------------------------------------------------------------------------


def figure_votes_par_bloc(table: pd.DataFrame) -> plt.Figure:
    """Part de votes « pour » sur l'ensemble du texte, par bloc politique."""
    donnees = table[table["a_vote"]]
    croise = (donnees.pivot_table(index="bloc", columns="texte_cle",
                                  values="vote_pour", aggfunc="mean") * 100)
    croise = croise.reindex(_ordonner(croise.index))

    fig, ax = plt.subplots(figsize=(8, 4.2))
    largeur = 0.8 / max(len(croise.columns), 1)
    x = np.arange(len(croise))
    for k, colonne in enumerate(croise.columns):
        ax.bar(x + k * largeur - 0.4 + largeur / 2, croise[colonne], width=largeur,
               label=colonne, color=COULEURS_TEXTES.get(colonne, "#777777"))
    ax.set_xticks(x, _etiquettes_blocs(croise.index), fontsize=8.5)
    ax.set_ylabel("% de votes « pour »")
    ax.set_ylim(0, 105)
    ax.legend(title="texte")
    _habiller(ax, "Le vote final se lit entièrement dans l'appartenance de bloc",
              "part de votes favorables à l'ensemble du texte (votes exprimés)",
              "Source : scrutins publics, Assemblée nationale, XVIIe législature.")
    return fig


def figure_dissidence(table_dissidence: pd.DataFrame) -> plt.Figure:
    """Taux de dissidence par bloc et par texte, sur les votes d'amendements."""
    croise = (table_dissidence.pivot_table(index="bloc", columns="texte_cle",
                                           values="dissident", aggfunc="mean") * 100)
    croise = croise.reindex(_ordonner(croise.index))

    fig, ax = plt.subplots(figsize=(8, 4.2))
    largeur = 0.8 / max(len(croise.columns), 1)
    x = np.arange(len(croise))
    for k, colonne in enumerate(croise.columns):
        ax.bar(x + k * largeur - 0.4 + largeur / 2, croise[colonne], width=largeur,
               label=colonne, color=COULEURS_TEXTES.get(colonne, "#777777"))
    ax.set_xticks(x, _etiquettes_blocs(croise.index), fontsize=8.5)
    ax.set_ylabel("% de votes s'écartant de la majorité du groupe")
    ax.legend(title="texte")
    _habiller(ax, "C'est dans les votes d'amendements que la discipline se fissure",
              "taux de dissidence par bloc, sur les scrutins d'amendements des trois textes",
              "Source : scrutins publics AN. La dissidence compare le vote du député à la "
              "position majoritaire de son groupe sur le même scrutin.")
    return fig


# --------------------------------------------------------------------------
# 4. Proximité lexicale avec les demandes des lobbies
# --------------------------------------------------------------------------


def figure_proximite(table: pd.DataFrame) -> plt.Figure:
    """Distribution de la proximité lexicale, par bloc, chez les auteurs d'amendements."""
    donnees = table[table["a_depose_amendement"] & table["proximite_max"].gt(0)]
    blocs = _ordonner(donnees["bloc"].dropna().unique())
    echantillons = [donnees.loc[donnees["bloc"] == b, "proximite_max"].to_numpy()
                    for b in blocs]

    fig, ax = plt.subplots(figsize=(8, 4.2))
    parties = ax.violinplot(echantillons, showmedians=True, widths=0.8)
    for corps, bloc in zip(parties["bodies"], blocs, strict=True):
        corps.set_facecolor(COULEURS_BLOCS.get(bloc, "#999999"))
        corps.set_alpha(0.75)
    for cle in ("cmedians", "cbars", "cmins", "cmaxes"):
        if cle in parties:
            parties[cle].set_color("#333333")
    ax.set_xticks(range(1, len(blocs) + 1), _etiquettes_blocs(blocs), fontsize=8.5)
    ax.set_ylabel("proximité lexicale maximale (cosinus TF-IDF)")
    for i, echantillon in enumerate(echantillons, start=1):
        ax.annotate(f"n={len(echantillon)}", xy=(i, 1), xycoords=("data", "axes fraction"),
                    xytext=(0, -12), textcoords="offset points",
                    ha="center", fontsize=8, color="#555555")
    _habiller(ax, "Des distributions de proximité très semblables d'un bloc à l'autre",
              "députés ayant déposé au moins un amendement sur l'un des trois textes",
              "Lecture : proximité entre les exposés des motifs d'un député et les objets "
              "déclarés des lobbies du secteur. Convergence de discours, pas preuve de contact.")
    return fig


# --------------------------------------------------------------------------
# 5. Graphe biparti lobbies ↔ députés
# --------------------------------------------------------------------------


def figure_graphe_biparti(aretes: pd.DataFrame, deputes: pd.DataFrame,
                          *, titre_texte: str = "", min_degre: int = 3,
                          max_organisations: int = 22,
                          graine: int | None = None) -> tuple[plt.Figure, nx.Graph]:
    """Graphe biparti organisations ↔ députés, députés colorés par bloc.

    On ne garde que les organisations reliées à au moins `min_degre` députés :
    les milliers de liens uniques rendraient la figure illisible sans rien
    apporter.
    """
    graine = config.ALEA if graine is None else graine
    blocs = deputes.set_index("acteur_ref")["bloc"].to_dict()
    noms = deputes.set_index("acteur_ref")["nom_complet"].to_dict()

    # Le seuil de degré est adaptatif : on l'abaisse tant que la figure serait
    # trop pauvre. Un texte très ciblé (agriculture) se lit en gardant les
    # organisations liées à 3 députés ; un texte peu ciblé (défense) n'a que des
    # liens uniques, et les écarter viderait le graphe.
    degres = aretes.groupby("denomination")["acteur_ref"].nunique().sort_values(ascending=False)
    gardees: set[str] = set()
    for seuil in range(min_degre, 0, -1):
        gardees = set(degres[degres >= seuil].head(max_organisations).index)
        if len(gardees) >= 8:
            break
    filtrees = aretes[aretes["denomination"].isin(gardees)]

    graphe = nx.Graph()
    for _, ligne in filtrees.iterrows():
        organisation = "🏛 " + textwrap.fill(
            textwrap.shorten(ligne["denomination"].title(), 34, placeholder="…"), 18)
        depute = noms.get(ligne["acteur_ref"], ligne["acteur_ref"])
        graphe.add_node(organisation, type="organisation")
        graphe.add_node(depute, type="depute", bloc=blocs.get(ligne["acteur_ref"], "autre"))
        graphe.add_edge(organisation, depute, weight=float(ligne["poids"]))

    if graphe.number_of_nodes() == 0:
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.text(0.5, 0.5, "aucune arête au-dessus du seuil", ha="center", va="center")
        ax.axis("off")
        return fig, graphe

    organisations = [n for n, d in graphe.nodes(data=True) if d["type"] == "organisation"]
    positions = nx.spring_layout(graphe, k=1.1, iterations=400, seed=graine,
                                 weight="weight")

    fig, ax = plt.subplots(figsize=(11, 8.5))
    poids = np.array([graphe[u][v]["weight"] for u, v in graphe.edges()])
    nx.draw_networkx_edges(graphe, positions, ax=ax, alpha=0.35,
                           width=0.5 + 4 * poids / poids.max(), edge_color="#999999")
    nx.draw_networkx_nodes(
        graphe, positions, ax=ax, nodelist=organisations,
        node_color="#d9a13b", node_shape="s", edgecolors="#6b4f14", linewidths=0.6,
        node_size=[90 + 55 * graphe.degree(n) for n in organisations])
    deputes_noeuds = [n for n, d in graphe.nodes(data=True) if d["type"] == "depute"]
    nx.draw_networkx_nodes(
        graphe, positions, ax=ax, nodelist=deputes_noeuds,
        node_color=[COULEURS_BLOCS.get(graphe.nodes[n]["bloc"], "#999999")
                    for n in deputes_noeuds],
        node_size=70, edgecolors="white", linewidths=0.5)
    # Les noms sont posés légèrement au-dessus du carré, pour ne pas le masquer.
    etendue = max(np.ptp([p[1] for p in positions.values()]), 1e-6)
    positions_etiquettes = {n: (x, y + 0.045 * etendue) for n, (x, y) in positions.items()}
    etiquettes = nx.draw_networkx_labels(
        graphe, positions_etiquettes, ax=ax,
        labels={n: n.replace("🏛 ", "") for n in organisations},
        font_size=7, font_weight="bold")
    for texte_graphique in etiquettes.values():
        # Liseré blanc : les noms restent lisibles par-dessus les arêtes.
        texte_graphique.set_path_effects(
            [patheffects.withStroke(linewidth=2.6, foreground="white")])
    ax.axis("off")
    ax.set_title(f"Grappes d'influence déclarée{(' — ' + titre_texte) if titre_texte else ''}",
                 loc="left", fontweight="bold")
    poignees = [plt.Line2D([], [], marker="o", ls="", color=COULEURS_BLOCS[b], label=b)
                for b in ORDRE_BLOCS if b in {graphe.nodes[n]["bloc"] for n in deputes_noeuds}]
    poignees.append(plt.Line2D([], [], marker="s", ls="", color="#d9a13b",
                               label="organisation inscrite au répertoire"))
    ax.legend(handles=poignees, loc="lower left", fontsize=8)
    ax.text(0, -0.04,
            "Une arête relie une organisation à un député dont les amendements emploient "
            "un vocabulaire proche de l'objet qu'elle a déclaré.\nElle ne signifie pas qu'un "
            "contact a eu lieu : le répertoire HATVP ne nomme jamais le député approché.",
            transform=ax.transAxes, fontsize=7.5, color="#777777", va="top")
    logger.info("graphe tracé : %d nœuds (%d organisations), %d arêtes",
                graphe.number_of_nodes(), len(organisations), graphe.number_of_edges())
    return fig, graphe


def metriques_graphe(graphe: nx.Graph) -> pd.DataFrame:
    """Quelques mesures de centralité, pour commenter le graphe plutôt que l'admirer."""
    if graphe.number_of_nodes() == 0:
        return pd.DataFrame()
    degre = nx.degree_centrality(graphe)
    intermediarite = nx.betweenness_centrality(graphe, weight="weight")
    table = pd.DataFrame({
        "noeud": list(graphe.nodes()),
        "type": [graphe.nodes[n]["type"] for n in graphe.nodes()],
        "degre": [graphe.degree(n) for n in graphe.nodes()],
        "centralite_degre": [degre[n] for n in graphe.nodes()],
        "centralite_intermediarite": [intermediarite[n] for n in graphe.nodes()],
    })
    return table.sort_values("degre", ascending=False).reset_index(drop=True)


# --------------------------------------------------------------------------
# 6. Coefficients du modèle
# --------------------------------------------------------------------------


def figure_coefficients(coefficients: pd.DataFrame, *, titre: str,
                        exclure_intercept: bool = True) -> plt.Figure:
    """Graphique en forêt des odds ratios, échelle logarithmique."""
    table = coefficients.copy()
    if exclure_intercept:
        table = table[~table.index.str.contains("Intercept")]
    table = table.iloc[::-1]

    fig, ax = plt.subplots(figsize=(7.5, 0.42 * len(table) + 1.8))
    y = np.arange(len(table))
    couleurs = ["#1f3b63" if s else "#aaaaaa" for s in table["significatif"]]
    ax.hlines(y, table["or_ic_bas"], table["or_ic_haut"], color=couleurs, lw=2)
    ax.scatter(table["odds_ratio"], y, color=couleurs, zorder=3, s=36)
    ax.axvline(1, color="#444444", ls="--", lw=1)
    ax.set_yticks(y, [_etiquette(i) for i in table.index], fontsize=9)
    ax.set_xscale("log")
    ax.set_xlabel("odds ratio (échelle log) — à droite de 1 : effet positif")
    ax.grid(axis="y", visible=False)
    _habiller(ax, titre, "point = odds ratio, barre = intervalle de confiance à 95 % ; "
                         "en bleu, les effets significatifs au seuil de 5 %",
              "Écarts-types groupés par député.")
    return fig


# --------------------------------------------------------------------------
# 7. Test placebo
# --------------------------------------------------------------------------


def figure_placebo(amendements: pd.DataFrame) -> plt.Figure:
    """Proximité réelle contre proximité témoin, texte par texte.

    Si la mesure ne captait que « cet amendement est écrit en français
    administratif dense », les deux distributions se superposeraient. Les corpus
    comparés ont été ramenés à la même taille, sinon le maximum d'une similarité
    sur plus de documents gagnerait mécaniquement.
    """
    donnees = amendements[amendements["texte_exploitable"]]
    cles = [c for c in config.TEXTES_ANALYSE if c in set(donnees["texte_cle"])]
    fig, axes = plt.subplots(1, len(cles), figsize=(4.1 * len(cles), 3.9), sharey=True)
    axes = np.atleast_1d(axes)

    for ax, cle in zip(axes, cles, strict=True):
        sous = donnees[donnees["texte_cle"] == cle]
        bornes = np.linspace(0, max(sous[["proximite_lobby", "proximite_placebo"]].max().max(), 0.01), 28)
        ax.hist(sous["proximite_placebo"].dropna(), bins=bornes, color="#c9c0a8",
                label="témoin (autre secteur)", alpha=0.95)
        ax.hist(sous["proximite_lobby"].dropna(), bins=bornes, histtype="step",
                color="#1f3b63", lw=2, label="lobbies du texte")
        ax.axvline(sous["proximite_placebo"].mean(), color="#8a7f62", ls=":", lw=1.4)
        ax.axvline(sous["proximite_lobby"].mean(), color="#1f3b63", ls="--", lw=1.4)
        ax.set_title(cle, loc="left", fontsize=10.5)
        ax.set_xlabel("proximité lexicale")
        ecart = sous["proximite_lobby"].mean() - sous["proximite_placebo"].mean()
        ax.annotate(f"écart des moyennes\n+{ecart:.3f}", xy=(0.97, 0.9), xycoords="axes fraction",
                    ha="right", fontsize=8.5, color="#444444")
    axes[0].set_ylabel("nombre d'amendements")
    axes[0].legend(fontsize=8.5, loc="center right")
    fig.suptitle("La proximité mesurée est bien sectorielle, pas stylistique",
                 x=0.005, ha="left", fontweight="bold", fontsize=12)
    fig.text(0.005, -0.02,
             "Lecture : pour chaque amendement, similarité maximale avec les objets déclarés des "
             "lobbies ayant nommé le texte (trait bleu)\net avec ceux d'un autre texte de l'étude "
             "(aplat beige), sur des corpus ramenés à la même taille.",
             fontsize=7.5, color="#777777", va="top")
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------------
# 8. Intérêts déclarés par les députés
# --------------------------------------------------------------------------


def figure_secteurs_interets(profil: pd.DataFrame) -> plt.Figure:
    """Secteurs dans lesquels les députés déclarent un intérêt privé, par bloc."""
    secteurs = [c for c in profil.columns if c.isupper() and c != "NI"]
    totaux = profil[secteurs].sum().sort_values(ascending=True)
    blocs = _ordonner(profil["bloc"].dropna().unique())

    fig, ax = plt.subplots(figsize=(8, 0.42 * len(totaux) + 2.2))
    gauche = np.zeros(len(totaux))
    for bloc in blocs:
        part = profil.loc[profil["bloc"] == bloc, totaux.index].sum().to_numpy()
        ax.barh(totaux.index, part, left=gauche, color=COULEURS_BLOCS.get(bloc, "#999999"),
                label=bloc, height=0.72)
        gauche += part
    for i, total in enumerate(totaux):
        ax.text(total + 2, i, f"{int(total)}", va="center", fontsize=8.5, color="#444444")
    ax.set_xlabel("nombre de députés déclarant au moins un intérêt privé dans le secteur")
    ax.grid(axis="y", visible=False)
    ax.legend(fontsize=8, ncol=3, loc="lower right")
    _habiller(ax, "Les députés déclarent surtout des intérêts dans l'immobilier et le secteur public local",
              f"{len(profil)} députés ; rubriques privées uniquement "
              "(emplois des cinq dernières années, participations, direction, bénévolat)",
              "Source : déclarations d'intérêts et d'activités HATVP, classées par lexique "
              "sectoriel. 34 % des libellés sont rattachés à un secteur : les autres sont "
              "trop vagues pour être classés.")
    return fig


# --------------------------------------------------------------------------
# 9. Robustesse
# --------------------------------------------------------------------------


def figure_sensibilite_fenetre(sensibilite: pd.DataFrame) -> plt.Figure:
    """Coefficient d'exposition et volume retenu, selon la largeur de fenêtre."""
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    ax.plot(sensibilite["marge_mois"], sensibilite["coef_proximite"],
            marker="o", color="#1f3b63", label="coefficient de proximité")
    significatif = sensibilite["p_proximite"] < 0.05
    ax.scatter(sensibilite.loc[significatif, "marge_mois"],
               sensibilite.loc[significatif, "coef_proximite"],
               color="#b03a2e", zorder=4, s=70, label="significatif à 5 %")
    ax.axhline(0, color="#444444", ls="--", lw=1)
    ax.set_xlabel("marge appliquée autour de la fenêtre de débat (mois)")
    ax.set_ylabel("coefficient logit de la proximité")
    ax.set_ylim(min(0, sensibilite["coef_proximite"].min() * 1.4),
                max(sensibilite["coef_proximite"].max() * 1.4, 0.02))

    secondaire = ax.twinx()
    secondaire.bar(sensibilite["marge_mois"], sensibilite["activites_niveau_1"],
                   width=1.4, color="#d9a13b", alpha=0.3, zorder=0)
    secondaire.set_ylabel("activités de niveau 1 retenues", color="#8a6d20")
    secondaire.grid(visible=False)
    for _, ligne in sensibilite.iterrows():
        ax.annotate(f"p={ligne['p_proximite']:.2f}",
                    xy=(ligne["marge_mois"], ligne["coef_proximite"]),
                    xytext=(0, 9), textcoords="offset points",
                    ha="center", fontsize=8, color="#555555")
    ax.legend(loc="lower right", fontsize=8.5)
    _habiller(ax, "Le résultat ne tient pas à la largeur de fenêtre choisie",
              "coefficient de la proximité lexicale dans le modèle de dissidence, "
              "pour cinq largeurs de fenêtre temporelle",
              "Le volume d'activités retenues varie de 184 à 256 ; le coefficient reste "
              "entre 0,06 et 0,09 et n'atteint jamais le seuil de 5 %.")
    return fig

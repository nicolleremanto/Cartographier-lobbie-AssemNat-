"""Chemins, paramètres et nomenclatures du projet.

Un seul endroit pour les constantes : les autres modules importent d'ici.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# Arborescence
# --------------------------------------------------------------------------
# Racine = dossier qui contient src/, data/, notebooks/.
ROOT = Path(os.environ.get("LOBBYNOMICS_ROOT", Path(__file__).resolve().parents[2]))

DATA = ROOT / "data"
RAW = DATA / "raw"          # fichiers téléchargés tels quels (jamais modifiés)
INTERIM = DATA / "interim"  # décompressions et étapes intermédiaires
PROCESSED = DATA / "processed"  # tables propres, versionnables si petites
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"

for _d in (RAW, INTERIM, PROCESSED, REPORTS, FIGURES):
    _d.mkdir(parents=True, exist_ok=True)

LEGISLATURE = "17"

# --------------------------------------------------------------------------
# Sources de données (URL publiques, aucune authentification)
# --------------------------------------------------------------------------
SOURCES: dict[str, dict[str, str]] = {
    "hatvp_repertoire": {
        "url": "https://www.hatvp.fr/agora/opendata/agora_repertoire_opendata.json",
        "filename": "hatvp_repertoire.json",
        "kind": "json",
        "description": "Répertoire des représentants d'intérêts : fiches + activités déclarées.",
    },
    "hatvp_liste": {
        "url": "https://www.hatvp.fr/livraison/opendata/liste.csv",
        "filename": "hatvp_liste.csv",
        "kind": "csv",
        "description": "Index des déclarations des responsables publics (DI, DIA, DSP).",
    },
    "hatvp_declarations": {
        "url": "https://www.hatvp.fr/livraison/merge/declarations.xml",
        "filename": "hatvp_declarations.xml",
        "kind": "xml",
        "description": "Contenu des déclarations d'intérêts et d'activités.",
    },
    "an_scrutins": {
        "url": f"https://data.assemblee-nationale.fr/static/openData/repository/{LEGISLATURE}/loi/scrutins/Scrutins.json.zip",
        "filename": "an_scrutins.json.zip",
        "kind": "zip",
        "description": "Scrutins publics de la XVIIe législature, vote nominatif par député.",
    },
    "an_amendements": {
        "url": f"https://data.assemblee-nationale.fr/static/openData/repository/{LEGISLATURE}/loi/amendements_div_legis/Amendements.json.zip",
        "filename": "an_amendements.json.zip",
        "kind": "zip",
        "description": "Amendements déposés en commission et en séance, auteur et sort.",
    },
    "an_dossiers": {
        "url": f"https://data.assemblee-nationale.fr/static/openData/repository/{LEGISLATURE}/loi/dossiers_legislatifs/Dossiers_Legislatifs.json.zip",
        "filename": "an_dossiers.json.zip",
        "kind": "zip",
        "description": "Dossiers législatifs : titres, étapes, textes associés.",
    },
    "an_acteurs": {
        "url": f"https://data.assemblee-nationale.fr/static/openData/repository/{LEGISLATURE}/amo/tous_acteurs_mandats_organes_xi_legislature/AMO30_tous_acteurs_tous_mandats_tous_organes_historique.json.zip",
        "filename": "an_acteurs.json.zip",
        "kind": "zip",
        "description": "Acteurs, mandats et organes : identité des députés, groupes, commissions.",
    },
    "geo_communes": {
        "url": "https://geo.api.gouv.fr/communes?fields=code,nom,population,surface,departement&format=json",
        "filename": "geo_communes.json",
        "kind": "json",
        "description": "API Géo (Etalab) : population et surface de chaque commune, "
                       "pour construire un indicateur rural/urbain par département.",
    },
}

# --------------------------------------------------------------------------
# Textes de loi retenus
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TexteCible:
    """Un texte de loi étudié, et la façon de le relier au répertoire HATVP."""

    cle: str                       # identifiant court utilisé dans tout le projet
    dossier_ref: str               # uid du dossier législatif (clé de jointure interne AN)
    libelle: str                   # titre tel qu'il apparaît dans les scrutins
    secteurs_hatvp: tuple[str, ...]      # codes « secteur d'activité » du répertoire
    domaines_hatvp: tuple[str, ...]      # libellés « domaine d'intervention » des activités
    mots_cles: tuple[str, ...]           # vocabulaire attendu dans l'objet des activités
    alias: tuple[str, ...]               # façons dont le texte est nommé en clair par les lobbies
    sens_pro_lobby: str                  # ce que le lobby sectoriel dominant demandait
    note: str = ""

    @property
    def secteur_principal(self) -> str:
        return self.secteurs_hatvp[0]


TEXTES_CIBLES: tuple[TexteCible, ...] = (
    TexteCible(
        cle="agriculture",
        dossier_ref="DLR5L17N54085",
        libelle="Projet de loi d’urgence pour la protection et la souveraineté agricoles",
        secteurs_hatvp=("AGRI", "ENVIRONNEMENT", "CONSO", "RESOURNAT"),
        domaines_hatvp=(
            "Agriculture, agroalimentaire",
            "Agriculture",
            "Industrie agroalimentaire",
            "Produits phytosanitaires",
            "Elevage",
            "Pêche",
            "Environnement",
        ),
        mots_cles=(
            "agricole", "agriculture", "agroalimentaire", "phytosanitaire",
            "pesticide", "acetamipride", "neonicotinoide", "elevage", "eleveur",
            "exploitation agricole", "foncier agricole", "pac", "souverainete alimentaire",
            "egalim", "filiere", "irrigation", "retenue d eau", "haie", "zan",
        ),
        alias=(
            "loi d urgence agricole", "projet de loi d urgence agricole",
            "pjl urgence agricole", "urgence pour la protection et la souverainete agricoles",
            "loi d urgence pour la protection", "souverainete agricole",
            "souverainete agricoles", "urgence agricole",
            # Ajouté après l'audit manuel : une activité nommait le texte
            # « PJL Agricole », forme absente de la liste initiale (cf. docs/methode.md).
            "pjl agricole", "projet de loi agricole",
        ),
        sens_pro_lobby="assouplissement des contraintes environnementales pesant sur la production",
        note="Texte le plus voté de la législature (422 scrutins) ; lobbying agricole et "
             "environnemental tous deux très documentés.",
    ),
    TexteCible(
        cle="defense",
        dossier_ref="DLR5L17N54083",
        libelle="Projet de loi actualisant la programmation militaire pour les années 2024 à 2030 "
                "et portant diverses dispositions intéressant la défense",
        secteurs_hatvp=("SECURITE", "AERONOSP", "RECHERCHE"),
        domaines_hatvp=(
            "Défense, sécurité", "Défense", "Industrie de défense",
            "Aéronautique, aérospatiale", "Politique industrielle",
        ),
        mots_cles=(
            "defense", "militaire", "armement", "armee", "lpm",
            "programmation militaire", "base industrielle et technologique de defense",
            "bitd", "souverainete industrielle", "aeronautique", "spatial", "drone",
            "cyberdefense", "munition",
        ),
        alias=(
            "lpm", "loi de programmation militaire", "programmation militaire",
            "actualisation de la lpm", "lpm 2024 2030", "lpm 2024-2030",
            "projet de loi de programmation militaire", "actualisation de la loi de programmation",
        ),
        sens_pro_lobby="hausse et sécurisation pluriannuelle de la commande publique de défense",
        note="Industrie de défense : lobbying concentré sur peu d'acteurs, très identifiables.",
    ),
    TexteCible(
        cle="fraudes",
        dossier_ref="DLR5L17N52985",
        libelle="Projet de loi relatif à la lutte contre les fraudes sociales et fiscales",
        secteurs_hatvp=("FINANCES", "FINANCE", "PROREG", "ENTREPRISE", "ECONOMIE"),
        domaines_hatvp=(
            "Finances publiques", "Banques, assurances, secteur financier",
            "Entreprises et professions libérales", "Taxes", "Budget",
            "Gouvernance d’entreprise", "PME/TPE",
        ),
        mots_cles=(
            "fraude fiscale", "fraude sociale", "evasion fiscale", "controle fiscal",
            "secret professionnel", "secret bancaire", "tracfin", "urssaf",
            "travail dissimule", "sanction administrative", "obligation declarative",
            "beneficiaire effectif", "cotisation sociale",
        ),
        alias=(
            "fraude sociale et fiscale", "fraudes sociales et fiscales",
            "fraude sociale et fiscales", "pjl fraude", "projet de loi fraude",
            "lutte contre la fraude sociale", "lutte contre les fraudes sociales",
            "loi de lutte contre la fraude", "pjl fraudes",
        ),
        sens_pro_lobby="limitation des nouvelles obligations déclaratives et des pouvoirs de contrôle",
        note="Cas de contre-lobbying : les professions réglementées défendent le secret professionnel.",
    ),
    TexteCible(
        cle="logement",
        dossier_ref="DLR5L17N54144",
        libelle="Pour la mobilisation de l’habitat existant en réponse à la crise du logement",
        secteurs_hatvp=("AMENAGEMENT", "CONSO", "ECONOMIE"),
        domaines_hatvp=(
            "Construction, logement, aménagement du territoire", "Logement",
            "Urbanisme", "Immobilier",
        ),
        mots_cles=(
            "logement", "habitat", "immobilier", "location", "meuble de tourisme",
            "bailleur", "locataire", "copropriete", "renovation energetique",
            "passoire thermique", "dpe", "encadrement des loyers", "logement social",
        ),
        alias=(
            "mobilisation de l habitat existant", "habitat existant",
            "ppl habitat existant", "mobilisation de l habitat",
        ),
        sens_pro_lobby="préservation de la rentabilité locative et assouplissement des calendriers de rénovation",
        note="Texte plus petit, gardé comme cas de contrôle (moins de scrutins).",
    ),
)

TEXTES_PAR_CLE: dict[str, TexteCible] = {t.cle: t for t in TEXTES_CIBLES}
TEXTES_PAR_DOSSIER: dict[str, TexteCible] = {t.dossier_ref: t for t in TEXTES_CIBLES}

#: Textes sur lesquels on fait tourner la modélisation (les plus gros).
TEXTES_ANALYSE: tuple[str, ...] = ("agriculture", "defense", "fraudes")

# --------------------------------------------------------------------------
# Paramètres de matching
# --------------------------------------------------------------------------
SEUIL_FUZZY_SCRUTIN = 88     # score rapidfuzz minimal pour rattacher un scrutin à un dossier
SEUIL_FUZZY_ACTIVITE = 80    # idem pour une activité HATVP -> texte de loi
TAILLE_ECHANTILLON_AUDIT = 60  # nb de paires relues à la main pour estimer le taux d'erreur

#: Les activités HATVP ne sont datées qu'à l'exercice (l'année) : on considère
#: qu'une activité peut concerner un texte si son exercice recouvre la fenêtre
#: de débat élargie de ce nombre de mois.
MARGE_FENETRE_MOIS = 6

#: Groupes politiques regroupés en blocs, pour éviter 11 modalités quasi vides.
BLOCS_POLITIQUES: dict[str, str] = {
    "LFI-NFP": "gauche radicale",
    "LFI": "gauche radicale",
    "GDR": "gauche radicale",
    "SOC": "gauche",
    "ECOS": "gauche",
    "EcoS": "gauche",
    "LIOT": "centre",
    "DEM": "centre",
    "EPR": "centre",
    "HOR": "droite",
    "DR": "droite",
    "UDR": "droite radicale",
    "RN": "droite radicale",
    "NI": "non inscrit",
}

ALEA = 20261002  # graine aléatoire : tout tirage du projet est reproductible

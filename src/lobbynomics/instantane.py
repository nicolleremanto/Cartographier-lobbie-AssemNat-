"""Instantané des données du rapport : relancer le notebook sans 25 minutes de pipeline.

Le rapport a été produit à partir des sources officielles téléchargées le
2 octobre 2026. Deux façons de retrouver ses tables dans ``data/`` :

* **reconstruire** depuis les sources brutes, avec ``make pipeline`` (~700 Mo
  de téléchargement, ~25 minutes). L'open data de l'Assemblée et le répertoire
  HATVP changent tous les jours : les chiffres obtenus seront ceux du jour, pas
  forcément ceux commentés dans le rapport ;
* **récupérer l'instantané** des tables intermédiaires produites le 2 octobre
  (87 Mo), publié en *release* du dépôt GitHub et vérifié par son empreinte
  SHA-256 : on retrouve alors exactement les chiffres du rapport.

``preparer_donnees`` est appelée par la première cellule du notebook : si une
table manque, elle récupère l'instantané ; si tout est là, elle ne fait rien.
"""
from __future__ import annotations

import hashlib
import logging
import zipfile
from pathlib import Path

import requests

from . import config

logger = logging.getLogger(__name__)

URL = ("https://github.com/nicolleremanto/Cartographier-lobbie-AssemNat-/releases/"
       "download/donnees-2026-10-02/instantane_donnees_2026-10-02.zip")
SHA256 = "fe8999d09029d3022591e46dd4931b04fd46ed15e60aadf727e6a39f1fcc003b"

# Tables lues par le notebook et absentes de Git (trop lourdes ou intermédiaires).
TABLES = (
    "an_amendements", "an_deports", "an_deputes", "an_dossiers", "an_organes",
    "an_scrutins", "an_textes_dossiers", "an_votes", "deports_rattaches",
    "geo_departements", "hatvp_activites", "hatvp_index_declarations",
    "hatvp_interets_deputes", "hatvp_organisations", "interets_classes",
    "scrutins_rattaches",
)
MANIFESTE = config.RAW / "_manifeste.json"


def fichiers_manquants() -> list[Path]:
    """Les fichiers de l'instantané qui ne sont pas encore dans ``data/``."""
    attendus = [config.PROCESSED / f"{nom}.parquet" for nom in TABLES] + [MANIFESTE]
    return [chemin for chemin in attendus if not chemin.exists()]


def verifier_empreinte(archive: Path, attendue: str = SHA256) -> None:
    """Lève une erreur si l'archive n'est pas exactement celle publiée."""
    h = hashlib.sha256()
    with archive.open("rb") as fh:
        for bloc in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloc)
    if h.hexdigest() != attendue:
        raise ValueError(f"empreinte SHA-256 inattendue pour {archive.name} : "
                         f"{h.hexdigest()} au lieu de {attendue}")


def extraire(archive: Path, racine: Path = config.ROOT) -> list[str]:
    """Décompresse l'archive sous ``racine`` sans écraser un fichier existant.

    Ne pas écraser est délibéré : une table que l'utilisateur a reconstruite
    lui-même avec le pipeline prime sur l'instantané.
    """
    extraits = []
    with zipfile.ZipFile(archive) as zf:
        for membre in zf.infolist():
            if membre.is_dir():
                continue
            cible = (racine / membre.filename).resolve()
            if racine.resolve() not in cible.parents:  # archive malveillante
                raise ValueError(f"chemin hors du projet dans l'archive : {membre.filename}")
            if cible.exists():
                continue
            cible.parent.mkdir(parents=True, exist_ok=True)
            cible.write_bytes(zf.read(membre))
            extraits.append(membre.filename)
    return extraits


def preparer_donnees(*, url: str = URL, timeout: int = 120) -> list[str]:
    """Garantit que toutes les tables du notebook sont présentes.

    Ne télécharge rien si elles le sont déjà. Renvoie la liste des fichiers ajoutés.
    """
    manquants = fichiers_manquants()
    if not manquants:
        logger.info("toutes les tables sont présentes, rien à télécharger")
        return []

    logger.info("%d fichier(s) manquant(s) : récupération de l'instantané du 2 octobre 2026",
                len(manquants))
    archive = config.INTERIM / Path(url).name
    if not archive.exists():
        partiel = archive.with_suffix(".part")
        with requests.get(url, stream=True, timeout=timeout) as rep:
            rep.raise_for_status()
            with partiel.open("wb") as fh:
                for bloc in rep.iter_content(1 << 20):
                    fh.write(bloc)
        partiel.replace(archive)
    try:
        verifier_empreinte(archive)
    except ValueError:
        archive.unlink()  # téléchargement corrompu : on ne le garde pas
        raise
    extraits = extraire(archive)
    logger.info("%d fichier(s) extrait(s)", len(extraits))
    return extraits


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    preparer_donnees()

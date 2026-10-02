"""Étape 1 — récupération des données brutes.

Trois sources officielles, toutes en accès libre :

* le répertoire des représentants d'intérêts de la HATVP (qui déclare cibler quoi) ;
* les déclarations des responsables publics, HATVP également (ce que les députés déclarent) ;
* l'open data de l'Assemblée nationale (scrutins, amendements, dossiers, acteurs).

Le module est idempotent : un fichier déjà téléchargé et non vide n'est pas
retéléchargé, sauf `force=True`. C'est ce qui permet de relancer le pipeline
entier sans attendre 10 minutes de réseau.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import config

logger = logging.getLogger(__name__)

CHUNK = 1 << 20  # 1 Mo
MANIFESTE = config.RAW / "_manifeste.json"


def _sha256(path: Path, limite: int | None = None) -> str:
    h = hashlib.sha256()
    lu = 0
    with path.open("rb") as fh:
        while True:
            bloc = fh.read(CHUNK)
            if not bloc:
                break
            h.update(bloc)
            lu += len(bloc)
            if limite is not None and lu >= limite:
                break
    return h.hexdigest()


def telecharger(cle: str, *, force: bool = False, timeout: int = 60) -> Path:
    """Télécharge une source de `config.SOURCES` dans `data/raw/`."""
    if cle not in config.SOURCES:
        raise KeyError(f"source inconnue : {cle!r} (connues : {sorted(config.SOURCES)})")
    src = config.SOURCES[cle]
    cible = config.RAW / src["filename"]

    if cible.exists() and cible.stat().st_size > 0 and not force:
        logger.info("%s déjà présent (%.1f Mo), téléchargement sauté",
                    cible.name, cible.stat().st_size / 1e6)
        return cible

    logger.info("téléchargement de %s …", src["url"])
    tmp = cible.with_suffix(cible.suffix + ".part")
    with requests.get(src["url"], stream=True, timeout=timeout) as rep:
        rep.raise_for_status()
        with tmp.open("wb") as fh:
            for bloc in rep.iter_content(CHUNK):
                fh.write(bloc)
    tmp.replace(cible)
    logger.info("%s → %.1f Mo", cible.name, cible.stat().st_size / 1e6)
    return cible


def decompresser(cle: str, *, force: bool = False) -> Path:
    """Décompresse une source zip dans `data/interim/<cle>/`."""
    src = config.SOURCES[cle]
    if src["kind"] != "zip":
        raise ValueError(f"{cle} n'est pas une archive")
    archive = telecharger(cle)
    dossier = config.INTERIM / cle
    if dossier.exists() and any(dossier.rglob("*.json")) and not force:
        logger.info("%s déjà décompressé", cle)
        return dossier
    if force and dossier.exists():
        shutil.rmtree(dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(dossier)
    logger.info("%s → %d fichiers JSON", cle, sum(1 for _ in dossier.rglob("*.json")))
    return dossier


def tout_recuperer(*, force: bool = False) -> dict[str, dict]:
    """Télécharge les six sources et écrit un manifeste de provenance.

    Le manifeste (URL, taille, empreinte, horodatage) est la pièce qui rend la
    collecte vérifiable : il permet de dire *quelle* version des données a produit
    les résultats du rapport.
    """
    manifeste: dict[str, dict] = {}
    for cle, src in config.SOURCES.items():
        chemin = telecharger(cle, force=force)
        if src["kind"] == "zip":
            decompresser(cle, force=force)
        manifeste[cle] = {
            "url": src["url"],
            "fichier": chemin.name,
            "description": src["description"],
            "octets": chemin.stat().st_size,
            "sha256_premier_mo": _sha256(chemin, limite=CHUNK),
            "recupere_le": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    MANIFESTE.write_text(json.dumps(manifeste, ensure_ascii=False, indent=2), "utf-8")
    logger.info("manifeste écrit : %s", MANIFESTE)
    return manifeste


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    tout_recuperer()

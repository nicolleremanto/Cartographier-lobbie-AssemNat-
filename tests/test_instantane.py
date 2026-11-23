"""Tests de la récupération de l'instantané de données (sans réseau)."""
from __future__ import annotations

import hashlib
import zipfile

import pytest

from lobbynomics.instantane import extraire, verifier_empreinte


def _archive(tmp_path, membres: dict[str, bytes]):
    chemin = tmp_path / "instantane.zip"
    with zipfile.ZipFile(chemin, "w") as zf:
        for nom, contenu in membres.items():
            zf.writestr(nom, contenu)
    return chemin


def test_empreinte_correcte_acceptee(tmp_path):
    archive = _archive(tmp_path, {"data/processed/a.parquet": b"abc"})
    verifier_empreinte(archive, hashlib.sha256(archive.read_bytes()).hexdigest())


def test_empreinte_fausse_refusee(tmp_path):
    archive = _archive(tmp_path, {"data/processed/a.parquet": b"abc"})
    with pytest.raises(ValueError, match="empreinte"):
        verifier_empreinte(archive, "0" * 64)


def test_extraction_n_ecrase_pas_une_table_reconstruite(tmp_path):
    racine = tmp_path / "projet"
    (racine / "data/processed").mkdir(parents=True)
    (racine / "data/processed/a.parquet").write_bytes(b"reconstruite")
    archive = _archive(tmp_path, {"data/processed/a.parquet": b"instantane",
                                  "data/raw/_manifeste.json": b"{}"})

    extraits = extraire(archive, racine)

    assert extraits == ["data/raw/_manifeste.json"]
    assert (racine / "data/processed/a.parquet").read_bytes() == b"reconstruite"


def test_extraction_refuse_un_chemin_hors_du_projet(tmp_path):
    racine = tmp_path / "projet"
    racine.mkdir()
    archive = _archive(tmp_path, {"../evasion.txt": b"x"})
    with pytest.raises(ValueError, match="hors du projet"):
        extraire(archive, racine)

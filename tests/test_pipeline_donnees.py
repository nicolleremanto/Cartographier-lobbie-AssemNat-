"""Tests de assurer_donnees : le notebook doit pouvoir se lancer sur un clone propre.

Repris du correctif proposé par Ariane, étendu à l'instantané de données.
"""
import pytest
import requests

from lobbynomics import config, instantane, pipeline


@pytest.fixture
def dossiers(monkeypatch, tmp_path):
    raw, processed = tmp_path / "raw", tmp_path / "processed"
    raw.mkdir()
    processed.mkdir()
    monkeypatch.setattr(config, "RAW", raw)
    monkeypatch.setattr(config, "PROCESSED", processed)
    monkeypatch.setattr(instantane, "MANIFESTE", raw / "_manifeste.json")
    return raw, processed


def _remplir(raw, processed):
    (raw / "_manifeste.json").write_text("{}")
    for nom in pipeline.TABLES_NOTEBOOK:
        (processed / f"{nom}.parquet").write_bytes(b"x")


def _interdit(*a, **kw):
    raise AssertionError("ne doit pas être appelé")


def test_donnees_presentes_ne_relancent_rien(monkeypatch, dossiers):
    _remplir(*dossiers)
    monkeypatch.setattr(instantane, "preparer_donnees", _interdit)
    monkeypatch.setattr(pipeline, "executer", _interdit)
    assert pipeline.assurer_donnees() is None


def test_clone_neuf_recupere_l_instantane(monkeypatch, dossiers):
    monkeypatch.setattr(instantane, "preparer_donnees", lambda: _remplir(*dossiers))
    monkeypatch.setattr(pipeline, "executer", _interdit)
    assert pipeline.donnees_presentes() is False
    assert pipeline.assurer_donnees() == "instantane"
    assert pipeline.donnees_presentes() is True


@pytest.mark.parametrize("panne", [requests.ConnectionError("hors ligne"),
                                   ValueError("empreinte SHA-256 inattendue")])
def test_instantane_inaccessible_reconstruit_depuis_les_sources(monkeypatch, dossiers, panne):
    def echec():
        raise panne

    appels = []

    def faux_executer(etapes, **kw):  # remplace le vrai pipeline (réseau)
        appels.append(etapes)
        _remplir(*dossiers)

    monkeypatch.setattr(instantane, "preparer_donnees", echec)
    monkeypatch.setattr(pipeline, "executer", faux_executer)
    assert pipeline.assurer_donnees() == "pipeline"
    assert appels == [("collecte", "parsing", "matching", "features")]
    assert pipeline.donnees_presentes() is True

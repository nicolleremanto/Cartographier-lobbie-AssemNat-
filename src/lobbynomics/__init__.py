"""Cartographie de l'influence déclarée des lobbies sur le travail législatif.

Projet du cours « Python pour la data science » (ENSAE 2A). Le code est organisé
comme le raisonnement du rapport :

``collect``       récupération des sources officielles (HATVP, Assemblée, API Géo)
``parse_an``      mise à plat de l'open data de l'Assemblée nationale
``parse_hatvp``   mise à plat du répertoire des représentants d'intérêts
``matching``      rapprochement des bases — le cœur du travail, et sa validation
``features``      construction de la table d'analyse député × texte
``models``        régressions logistiques
``viz``           figures du rapport
``pipeline``      orchestration de bout en bout
"""
from __future__ import annotations

__version__ = "1.0.0"
__all__ = ["collect", "config", "features", "matching", "models", "parse_an",
           "parse_hatvp", "pipeline", "viz"]

# Consignes du cours, et où elles sont traitées

Source : <https://pythonds.linogaliana.fr/content/annexes/evaluation.html>,
complétée par le TP1, le document « Le projet : ce qu'on attend de vous » et les
courriels du cours (22 septembre, 12 et 23 octobre 2026).

## Cadre

* Groupes de 3 ; sujet libre mais **validé** par la chargée de TD (refusé s'il est
  trop guidé ou trop complexe).
* Livrables : un dépôt GitHub public, un notebook, une soutenance.
* **Rendu du dépôt : vendredi 27 novembre 2026, 23 h 59.**
* **Soutenance : vendredi 4 décembre 2026**, au créneau habituel du TP : dix minutes
  libres puis questions de la chargée de TD, à n'importe quel membre du groupe.
* Pas de modèle demandé : la modélisation ne fait plus partie du barème, on répond
  à une question avec des statistiques descriptives.
* Dépôt **GitHub public**, avec un historique de versions réel : les dépôts
  constitués d'un seul *upload* sont pénalisés, les commits fréquents et les
  pull requests valorisés.
* Projets Kaggle **interdits**, données Twitter/X **interdites**.
* Assistants de code autorisés, *vibe coding* non : chaque membre doit pouvoir
  expliquer chaque ligne.

## Barème ENSAE (20 points)

| Poste | Points | Où c'est traité |
| --- | --- | --- |
| Données : collecte et nettoyage | 4 | `collect.py`, `parse_an.py`, `parse_hatvp.py` — 8 fichiers, 4 producteurs, ~700 Mo, API + téléchargements + XML lu en flux + dédoublonnage (51 % de doublons dans les déclarations) |
| Analyse descriptive | 4 | notebook, parties 1 à 5 ; chaque chiffre et chaque figure sont commentés, 18 figures |
| Démarche scientifique et reproductibilité | 5 | `pipeline.py` en une commande, manifeste de provenance SHA-256, `quality.py` (24 contrôles), `robustesse.py` (sensibilité + déterminisme), test placebo, 67 tests, CI GitHub Actions (tests + exécution du notebook sur un clone neuf), `docs/methode.md` |
| Format du code | 2 | 12 modules, un par étape ; le notebook n'appelle que des fonctions |
| Soutenance | 5 | `docs/rapport-explicatif.pdf`, section « préparer la soutenance » |

## Points explicitement exigés, et leur traitement ici

* **« Le projet doit être reproductible sous peine de sanction forte »**, et
  « faire tourner toutes les cellules sans erreur est une condition sine qua non
  pour avoir la moyenne » → test rejoué tel que le décrit le cours (clone neuf →
  `pip install -r requirements.txt` → Run All) : la première cellule récupère
  l'instantané des données du rapport si une table manque, puis le notebook
  s'exécute de bout en bout en moins d'une minute. La CI rejoue ce test à chaque
  poussée. La chaîne complète depuis les sources brutes tient dans `make pipeline`.
* **Données accessibles par URL publique** → les sept sources sont des URL
  ouvertes, listées dans `config.SOURCES` et vérifiées par le manifeste.
* **Pas de fichiers volumineux dans Git** → `data/raw/` et `data/interim/` sont
  ignorés ; seules les tables d'analyse légères sont versionnées.
* **Dépendances déclarées** → `requirements.txt` et `pyproject.toml`.
* **Code propre, pas de copier-coller de cellule** → toute la logique est dans
  `src/lobbynomics/`, le notebook appelle des fonctions.
* **« Chaque résultat doit être interprété : pas la peine de faire un `describe`
  et de ne pas le commenter »** → chaque figure porte un titre qui est sa
  conclusion, et chaque sortie est suivie d'un commentaire.
* **Effort de collecte valorisé** (croisement de plusieurs sources, API,
  scraping multi-pages) → quatre producteurs de données, sept fichiers, une API,
  et surtout un travail de rapprochement sans clé commune, qui est le cœur du
  projet.
* **Au moins une dimension approfondie** → c'est le **matching**, avec sa
  validation chiffrée, son audit manuel, son test placebo et ses tests de sensibilité.

## Organisation

- [x] Dépôt GitHub public, poussé au fil du travail ; CI verte.
- [x] Dates confirmées par le cours : rendu le 27 novembre 2026 à 23 h 59,
      soutenance le 4 décembre 2026.
- [x] Notebook vérifié sur un clone neuf (installation puis Run All).
- [ ] Soutenance : 3 ou 4 graphiques, partir de la question, résultats clés
      seulement (voir `docs/rapport-explicatif.pdf`).

# Consignes du cours, et où elles sont traitées

Source : <https://pythonds.linogaliana.fr/content/annexes/evaluation.html>,
complétée par le TP1 et le courriel de la chargée de TD du 22 septembre 2026.

## Cadre

* Groupes de 2 à 3 personnes ; sujet libre mais **à faire valider** par la
  chargée de TD du cours.
* Dépôt **GitHub public**, avec un historique de versions réel : les dépôts
  constitués d'un seul *upload* sont pénalisés, les commits fréquents et les
  pull requests valorisés.
* Projets Kaggle **interdits**, données Twitter/X **interdites**.
* Assistants de code autorisés, à condition de comprendre et d'assumer le rendu ;
  un usage sans reprise apparente est sanctionné.

## Barème ENSAE (20 points)

| Poste | Points | Où c'est traité |
| --- | --- | --- |
| Données : collecte et nettoyage | 4 | `collect.py`, `parse_an.py`, `parse_hatvp.py` — 8 fichiers, 4 producteurs, ~700 Mo, API + téléchargements + XML lu en flux + dédoublonnage (51 % de doublons dans les déclarations) |
| Analyse descriptive | 4 | notebook, parties 1 à 5 ; chaque chiffre et chaque figure sont commentés, 18 figures |
| Démarche scientifique et reproductibilité | 5 | `pipeline.py` en une commande, manifeste de provenance SHA-256, `quality.py` (24 contrôles), `robustesse.py` (sensibilité + déterminisme), test placebo, 58 tests, CI GitHub Actions, `docs/methode.md` |
| Format du code | 2 | 11 modules, un par étape ; le notebook n'appelle que des fonctions |
| Soutenance | 5 | `docs/rapport-explicatif.pdf`, section « préparer la soutenance » |

## Points explicitement exigés, et leur traitement ici

* **« Le projet doit être reproductible sous peine de sanction forte »**, et
  « faire tourner toutes les cellules sans erreur est une condition sine qua non
  pour avoir la moyenne » → le notebook ne fait que relire `data/processed/` et
  s'exécute en moins d'une minute ; la chaîne complète tient dans une commande.
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

## À faire côté organisation

- [ ] Faire valider le sujet par la chargée de TD.
- [ ] S'inscrire sur le Google Sheet de constitution des groupes.
- [ ] Créer le dépôt GitHub public et y pousser **progressivement** (pas un
      unique dépôt final : l'historique est noté).
- [ ] Confirmer la date de rendu et la date de soutenance, laissées en « XX
      décembre » et « XX janvier » sur la page du cours au 2 octobre 2026.

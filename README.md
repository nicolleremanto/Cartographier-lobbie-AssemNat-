# Cartographier l'influence déclarée des lobbies sur le travail législatif

Projet du cours **Python pour la data science** (ENSAE, 2A — `CSC_4CS08_AE`).

On croise quatre sources officielles pour une seule question : **la présence déclarée de
lobbies sur un texte de loi laisse-t-elle une trace observable dans le travail et les
votes des députés ?**

* qui déclare avoir ciblé quel texte → **répertoire des représentants d'intérêts de la HATVP** ;
* qui a écrit quoi sur ce texte → **amendements de l'Assemblée nationale** ;
* qui a voté quoi → **scrutins publics nominatifs** ;
* ce que les députés déclarent eux-mêmes → **déclarations d'intérêts HATVP**.

L'angle n'est pas de « prouver la corruption » — ni faisable, ni défendable. Il est de
**cartographier une influence déclarée** et de mesurer honnêtement ce qu'on peut, et
surtout ce qu'on ne peut pas, en conclure.

## Le résultat en cinq lignes

1. Sur le **vote final**, la discipline de groupe explique tout : la règle « chacun vote
   comme son bloc » se trompe sur **3 votes sur 547** pour la loi agricole. Il n'y a rien
   de plus à expliquer à ce niveau, et un logit à effets fixes de bloc n'y converge pas.
2. Dans les **scrutins d'amendements**, 4,3 % des votes s'écartent du groupe. La proximité
   lexicale avec les demandes déclarées des lobbies y est associée à **+0,34 point** de
   probabilité de dissidence par écart-type — **non significatif** (p = 0,08), et stable
   pour toutes les largeurs de fenêtre testées.
3. Sur l'**adoption des amendements**, la proximité aux lobbies du texte n'a aucun effet,
   mais le **test placebo** est significativement négatif : la mesure sépare les
   amendements dans le sujet de ceux qui en sortent, et les hors-sujet sont rejetés.
4. Le seul résultat **bien identifié** ne concerne pas les lobbies mais les députés : un
   intérêt privé déclaré dans le secteur d'un texte multiplie par **1,7 à 3,0** la
   probabilité d'y déposer un amendement. Spécialisation ou conflit d'intérêts ? Ces
   données ne tranchent pas.
5. Le travail utile est ailleurs : **rendre les bases comparables**. Le rattachement
   scrutin → dossier atteint 99,5 % de précision après arbitrage temporel ; le
   rapprochement HATVP → texte n'est fiable qu'à condition d'exiger que le texte soit
   **nommé** (100 % sur 20 paires relues à la main, contre 6 % pour un simple voisinage
   thématique).

## Les données

| Source | Volume récupéré | Ce qu'on en tire |
| --- | --- | --- |
| Répertoire HATVP des représentants d'intérêts | 4 094 organisations, **113 075 activités déclarées** | objet, domaine, secteur, type de décideur visé |
| Déclarations des responsables publics (HATVP) | 2 570 déclarations de députés, **11 438 intérêts déclarés** | anciens employeurs, participations, bénévolat |
| Scrutins publics, XVIIe législature | 8 455 scrutins, **1 273 091 votes nominatifs** | sens du vote de chaque député |
| Amendements, XVIIe législature | **126 392 amendements** | auteur, article visé, exposé des motifs, sort |
| Dossiers législatifs | 2 971 dossiers | titres, étapes, fenêtres de débat |
| Acteurs, mandats, organes, **déports** | 649 députés, 10 817 organes, 59 déports | groupe, commission, circonscription, **lien vers la fiche HATVP** |
| API Géo (Etalab) | 34 955 communes | densité et part rurale par département |

Environ **700 Mo** de sources brutes, aucune authentification, tout retéléchargeable par
une commande.

## Installation et exécution

```bash
git clone <url-du-depot>
cd projet-lobbies-assemblee
python -m venv .venv && source .venv/bin/activate
make installation

make pipeline        # collecte → parsing → matching → variables → qualité → modèles → robustesse → figures
```

Compter ~25 minutes la première fois (8 de téléchargement, 15 de mise à plat des 126 392
fichiers d'amendements), ~1 minute ensuite : rien n'est retéléchargé ni recalculé sans
raison. Les autres cibles :

```bash
make rapide     # tout sauf collecte et parsing
make qualite    # les 24 contrôles de qualité des données
make tests      # 58 tests
make rapport    # exécute le notebook de bout en bout
make            # la liste des cibles
```

Le rapport se lit dans `notebooks/rapport.ipynb`, qui ne fait que **relire** les tables de
`data/processed/` : aucune cellule ne retélécharge quoi que ce soit, et le notebook
s'exécute de bout en bout en moins d'une minute.

Une **intégration continue** (GitHub Actions) lance les tests à chaque poussée, sur Python
3.11 et 3.12. Elle ne télécharge aucune donnée : une CI qui dépend de 700 Mo d'open data
tombe en panne le jour où une source change d'URL, pour une raison étrangère au code.

## Organisation du dépôt

```
src/lobbynomics/
├── config.py       chemins, sources, textes de loi étudiés, nomenclatures
├── collect.py      téléchargement idempotent + manifeste de provenance
├── parse_an.py     mise à plat de l'open data Assemblée (le JSON y est retors)
├── parse_hatvp.py  mise à plat du répertoire, des déclarations et de l'API Géo
├── matching.py     rapprochement des bases, et sa validation chiffrée
├── features.py     tables d'analyse, proximité lexicale, test placebo
├── models.py       quatre régressions logistiques
├── quality.py      24 contrôles de qualité des données
├── robustesse.py   sensibilité aux choix arbitraires, déterminisme
├── viz.py          les 18 figures du rapport
└── pipeline.py     orchestration (python -m lobbynomics.pipeline)

notebooks/rapport.ipynb      le rapport
docs/methode.md              le détail méthodologique et ses limites
docs/sources.md              provenance, licences, dates de collecte
docs/journal.md              journal de bord : décisions, erreurs, prochaines étapes
docs/consignes.md            les consignes du cours et où elles sont traitées
docs/rapport-explicatif.pdf  présentation du projet en 23 pages
data/raw/                    sources brutes (hors Git)
data/processed/              tables propres en parquet
reports/figures/             les figures produites
tests/                       58 tests, centrés sur le matching et la qualité
```

## Les textes étudiés

Quatre textes de la XVIIe législature, choisis parce que le lobbying y est documenté et
les volumes suffisants :

| Clé | Texte | Scrutins | Amendements | Activités HATVP nommant le texte |
| --- | --- | --- | --- | --- |
| `agriculture` | Projet de loi d'urgence pour la protection et la souveraineté agricoles | 422 | 1 592 | 29 |
| `defense` | Projet de loi actualisant la programmation militaire 2024-2030 | 292 | 572 | 14 |
| `fraudes` | Projet de loi relatif à la lutte contre les fraudes sociales et fiscales | 262 | 747 | 165 |
| `logement` | Pour la mobilisation de l'habitat existant | 23 | 68 | **0** |

Le texte `logement` est conservé comme **cas témoin** : aucune activité HATVP ne le nomme,
alors que 419 activités lui sont thématiquement proches. C'est la démonstration la plus
simple que « proximité de thème » n'est pas « ciblage ».

## Ce que ce travail ne dit pas

Le répertoire HATVP ne nomme **jamais** le député approché, et ne date ses activités qu'à
l'année. Il n'existe donc aucune mesure d'un contact entre un lobby et un député. Ce qui
est mesuré est une **convergence de vocabulaire** entre les amendements d'un député et les
demandes publiquement déclarées d'une organisation. Elle peut venir d'une influence, d'une
conviction préexistante — un lobby approche d'abord les députés déjà convaincus — ou
simplement du jargon technique commun à un secteur.

Une seule source relie explicitement un député, un intérêt privé et un texte : les
**déports**. Il y en a 59 depuis 2017. `docs/methode.md` détaille toutes ces limites, y
compris celles de la déclaration HATVP elle-même, autodéclarative et contestée par
Transparency International.

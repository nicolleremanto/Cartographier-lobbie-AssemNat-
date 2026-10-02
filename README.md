# Cartographier l'influence déclarée des lobbies sur le travail législatif

Projet du cours **Python pour la data science** (ENSAE, 2A — `CSC_4CS08_AE`).

On croise trois sources officielles pour une seule question : **la présence
déclarée de lobbies sur un texte de loi laisse-t-elle une trace observable dans
le travail et les votes des députés ?**

* qui déclare avoir ciblé quel texte → **répertoire des représentants d'intérêts de la HATVP** ;
* qui a écrit quoi sur ce texte → **amendements de l'Assemblée nationale** ;
* qui a voté quoi → **scrutins publics nominatifs**.

L'angle n'est pas de « prouver la corruption » — ni faisable, ni défendable. Il
est de **cartographier une influence déclarée** et de mesurer honnêtement ce
qu'on peut, et surtout ce qu'on ne peut pas, en conclure.

## Le résultat en trois lignes

1. Sur le **vote final**, la discipline de groupe explique tout : la règle
   « chacun vote comme son bloc » se trompe sur **3 votes sur 547** pour la loi
   agricole. Il n'y a rien à expliquer de plus à ce niveau.
2. Dans les **scrutins d'amendements**, 4,3 % des votes s'écartent du groupe.
   La proximité lexicale entre les amendements d'un député et les demandes
   déclarées des lobbies y est associée à **+0,34 point de probabilité de
   dissidence** par écart-type — effet non significatif au seuil de 5 %
   (p = 0,08). On ne conclut donc pas.
3. Le travail utile est ailleurs : **rendre les trois bases comparables**. Le
   rattachement scrutin → dossier atteint 99,5 % de précision après arbitrage
   temporel ; le rapprochement HATVP → texte de loi n'est fiable qu'à condition
   d'exiger que le texte soit **nommé** (précision 100 % sur 20 paires relues à
   la main, contre 6 % pour un simple voisinage thématique).

## Les données

| Source | Volume récupéré | Ce qu'on en tire |
| --- | --- | --- |
| Répertoire HATVP des représentants d'intérêts | 4 094 organisations, **113 075 activités déclarées** | objet, domaine, secteur, type de décideur visé |
| Déclarations des responsables publics (HATVP) | 2 570 déclarations de députés, **11 438 intérêts déclarés** | anciens employeurs, participations, bénévolat |
| Scrutins publics, XVIIe législature | 8 455 scrutins, **1 273 091 votes nominatifs** | sens du vote de chaque député |
| Amendements, XVIIe législature | **126 392 amendements** | auteur, article visé, exposé des motifs, sort |
| Dossiers législatifs | 2 971 dossiers | titres, étapes, fenêtres de débat |
| Acteurs, mandats, organes | 649 députés, 10 817 organes | groupe, commission, circonscription, **lien vers la fiche HATVP** |
| API Géo (Etalab) | 34 955 communes | densité et part rurale par département |

Environ **700 Mo** de sources brutes, aucune authentification, tout
retéléchargeable par une commande.

## Installation et exécution

```bash
git clone <url-du-depot>
cd projet-lobbies-assemblee
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m lobbynomics.pipeline        # collecte → parsing → matching → modèles → figures
```

Compter ~10 minutes la première fois (dont 8 de téléchargement), ~30 secondes
ensuite : les fichiers déjà présents ne sont pas retéléchargés. Pour ne rejouer
qu'une partie :

```bash
python -m lobbynomics.pipeline --etapes matching features modeles figures
python -m lobbynomics.pipeline --force          # repart des sources en ligne
pytest                                           # 32 tests
```

Le rapport se lit dans `notebooks/rapport.ipynb`, qui ne fait que **relire** les
tables de `data/processed/` : aucune cellule ne retélécharge quoi que ce soit, et
le notebook s'exécute de bout en bout en moins d'une minute.

## Organisation du dépôt

```
src/lobbynomics/
├── config.py       chemins, sources, textes de loi étudiés, nomenclatures
├── collect.py      téléchargement idempotent + manifeste de provenance
├── parse_an.py     mise à plat de l'open data Assemblée (le JSON y est retors)
├── parse_hatvp.py  mise à plat du répertoire et des déclarations HATVP
├── matching.py     rapprochement des bases, et sa validation chiffrée
├── features.py     table d'analyse député × texte, proximité lexicale
├── models.py       trois régressions logistiques
├── viz.py          figures du rapport
└── pipeline.py     orchestration (python -m lobbynomics.pipeline)

notebooks/rapport.ipynb      le rapport
docs/methode.md              le détail méthodologique et ses limites
docs/sources.md              provenance, licences, dates de collecte
data/raw/                    sources brutes (hors Git)
data/processed/              tables propres en parquet
reports/figures/             figures produites
tests/                       32 tests, centrés sur le matching
```

## Les textes étudiés

Quatre textes de la XVIIe législature, choisis parce que le lobbying y est
documenté et les volumes suffisants :

| Clé | Texte | Scrutins | Amendements | Activités HATVP (texte nommé) |
| --- | --- | --- | --- | --- |
| `agriculture` | Projet de loi d'urgence pour la protection et la souveraineté agricoles | 422 | 1 592 | 29 |
| `defense` | Projet de loi actualisant la programmation militaire 2024-2030 | 292 | 572 | 14 |
| `fraudes` | Projet de loi relatif à la lutte contre les fraudes sociales et fiscales | 262 | 747 | 165 |
| `logement` | Pour la mobilisation de l'habitat existant | 23 | 68 | **0** |

Le texte `logement` est conservé comme **cas témoin** : aucune activité HATVP ne
le nomme, alors que 419 activités lui sont thématiquement proches. C'est la
démonstration la plus simple que « proximité de thème » n'est pas « ciblage ».

## Ce que ce travail ne dit pas

Le répertoire HATVP ne nomme **jamais** le député approché, et ne date ses
activités qu'à l'année. Il n'existe donc aucune mesure d'un contact entre un
lobby et un député. Ce qui est mesuré est une **convergence de vocabulaire**
entre les amendements d'un député et les demandes publiquement déclarées d'une
organisation. Elle peut venir d'une influence, d'une conviction préexistante —
un lobby approche d'abord les députés déjà convaincus — ou simplement du jargon
technique commun à un secteur. `docs/methode.md` détaille ces limites, y compris
celles de la déclaration HATVP elle-même, autodéclarative et contestée par
Transparency International.

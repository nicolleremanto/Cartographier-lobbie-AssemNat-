# Provenance des données

Toutes les sources sont publiques, en accès libre, sans authentification ni clé
d'API. Le manifeste `data/raw/_manifeste.json`, écrit par `collect.py`,
enregistre pour chaque fichier son URL, sa taille, une empreinte SHA-256 et
l'horodatage de récupération : c'est lui qui permet de dire quelle version des
données a produit les résultats du rapport.

Collecte de référence : **2 octobre 2026**.

## Haute Autorité pour la transparence de la vie publique (HATVP)

| Fichier | URL | Taille | Contenu |
| --- | --- | --- | --- |
| `hatvp_repertoire.json` | `https://www.hatvp.fr/agora/opendata/agora_repertoire_opendata.json` | 139 Mo | Répertoire des représentants d'intérêts : 4 094 organisations, 113 075 activités déclarées |
| `hatvp_liste.csv` | `https://www.hatvp.fr/livraison/opendata/liste.csv` | 3,2 Mo | Index de toutes les déclarations des responsables publics (13 065 lignes, dont 2 570 de députés) |
| `hatvp_declarations.xml` | `https://www.hatvp.fr/livraison/merge/declarations.xml` | 80 Mo | Contenu des déclarations : 5 976 déclarations, dont 1 147 de députés |

Licence : Licence Ouverte / Open Licence (Etalab).
Page de référence : <https://www.hatvp.fr/open-data/>

**Point d'attention.** `liste.csv` n'est pas le répertoire des lobbies — c'est
l'index des déclarations des élus. Les deux fichiers sont souvent confondus ; ils
servent ici à deux usages distincts (exposition sectorielle d'un côté, intérêts
déclarés des députés de l'autre).

## Assemblée nationale — open data

Toutes sous `https://data.assemblee-nationale.fr/static/openData/repository/17/`.

| Fichier | Chemin | Taille | Contenu |
| --- | --- | --- | --- |
| `an_scrutins.json.zip` | `loi/scrutins/Scrutins.json.zip` | 26 Mo | 8 455 scrutins, 1 273 091 votes nominatifs |
| `an_amendements.json.zip` | `loi/amendements_div_legis/Amendements.json.zip` | 304 Mo | 126 392 amendements avec exposé des motifs |
| `an_dossiers.json.zip` | `loi/dossiers_legislatifs/Dossiers_Legislatifs.json.zip` | 11 Mo | 2 971 dossiers de la XVIIe législature |
| `an_acteurs.json.zip` | `amo/tous_acteurs_mandats_organes_xi_legislature/AMO30_…json.zip` | 14 Mo | 649 députés, mandats, 10 817 organes, et **59 déports** (sous-dossier `deport/`) |

Licence : Licence Ouverte 2.0.
Page de référence : <https://data.assemblee-nationale.fr/>

**Les déports.** L'archive des acteurs contient un sous-dossier `deport/` rarement
exploité : 59 déclarations de conflit d'intérêts depuis 2017, où un député indique ne pas
vouloir prendre part au vote sur un texte donné. C'est la seule source du projet qui nomme
ensemble une personne, un intérêt privé et un texte. Le volume interdit toute statistique,
mais permet une vérification ligne à ligne contre les scrutins nominatifs.

**Pièges rencontrés.** Le JSON est une conversion automatique de XML : un champ
absent peut valoir `null`, `{"@xsi:nil": "true"}` ou `{"#text": "…"}` ; une liste
d'un seul élément devient un dict. Les fonctions `_txt` et `_liste` de
`parse_an.py` existent uniquement pour ça, et sont couvertes par des tests.
L'URL des amendements est `amendements_div_legis`, pas `amendements_legis` — la
seconde renvoie une 404 silencieuse.

## API Géo (Etalab)

| Fichier | URL | Taille | Contenu |
| --- | --- | --- | --- |
| `geo_communes.json` | `https://geo.api.gouv.fr/communes?fields=code,nom,population,surface,departement&format=json` | 4,1 Mo | 34 955 communes : population, superficie, département |

Licence : Licence Ouverte. Les surfaces sont en **hectares** (converties en km²
dans `parse_hatvp.charger_departements`).

Sert à construire deux indicateurs par département : la densité, et la part de
la population vivant dans une commune de moins de 2 000 habitants — indicateur
plus pertinent que la densité pour un vote agricole, où ce qui compte est le
nombre d'électeurs en petite commune, pas la moyenne tirée par une métropole.

## Ce qui n'est pas dans le dépôt Git

Les ~700 Mo de `data/raw/` et `data/interim/` sont exclus par `.gitignore` : un
dépôt n'est pas un espace de stockage, et les consignes du cours le rappellent.
Tout se reconstitue par :

```bash
python -m lobbynomics.pipeline --etapes collecte parsing
```

Les tables d'analyse légères de `data/processed/` sont, elles, versionnées, pour
que le notebook de rapport soit relisible sans attendre le téléchargement.

# Méthode, et ce qu'elle ne permet pas de dire

Document de référence du projet. Il raconte les décisions dans l'ordre où elles
ont été prises, y compris celles qui ont été annulées — c'est la partie du
travail qui ne se lit pas dans le code final.

---

## 1. Le problème, posé proprement

Trois bases, trois granularités, aucune clé commune.

| | Unité | Identifiant du texte de loi | Date |
| --- | --- | --- | --- |
| Scrutins | un vote de l'Assemblée | `dossierRef` **une fois sur trois seulement** | jour |
| Amendements | un amendement | `texteLegislatifRef` (toujours présent) | jour |
| Répertoire HATVP | une « activité » déclarée | **aucun** — un objet en texte libre | année d'exercice |

Tout le projet découle de cette dernière ligne. Le répertoire ne dit pas « j'ai
travaillé sur le dossier DLR5L17N54085 » ; il dit « Défendre les loups dans le
cadre de la loi d'urgence agricole ». Relier les deux est une **inférence**, et
la question honnête n'est pas « comment faire le lien » mais « quelle est la
probabilité que ce lien soit faux ».

---

## 2. Rattacher un scrutin à son dossier (interne à l'Assemblée)

### Le constat

Sur 8 455 scrutins de la XVIIe législature, **5 826 n'ont pas de lien explicite**
vers leur dossier législatif. Mais leur titre contient la dénomination du texte :

> « l'amendement n° 190 de M. Golliot après l'article 2 de la **proposition de
> loi visant à la nationalisation d'ArcelorMittal France** (première lecture). »

### La méthode

1. Extraire la dénomination après la dernière amorce (`du projet de loi`,
   `de la proposition de loi`, …), retirer les mentions de procédure.
2. Comparer aux titres des 2 971 dossiers avec `rapidfuzz.fuzz.token_set_ratio`.
3. **Arbitrer par la date** entre candidats à égalité de score.

### Pourquoi l'étape 3 existe

La première version s'arrêtait à l'étape 2 et plafonnait à **95,7 % de
précision**. En relisant les erreurs, le motif saute aux yeux : l'Assemblée ouvre
un dossier distinct par lecture, si bien que plusieurs dossiers portent
*exactement* le même titre. « Nationalisation d'ArcelorMittal France » existe
deux fois ; un score de 100 ne départage rien. En gardant les candidats à moins
de 3 points du meilleur et en retenant celui dont la fenêtre d'activité
parlementaire est la plus proche de la date du scrutin, la précision passe à
**99,5 %**.

### La mesure du taux d'erreur

Elle est gratuite : les **2 608 scrutins qui portent déjà un lien explicite** et
dont le titre est exploitable forment une vérité terrain. On leur applique quand
même la méthode floue et on compare.

| Seuil | Couverture | Précision |
| --- | --- | --- |
| 70 | 98,2 % | 84,6 % |
| 75 | 98,1 % | 84,6 % |
| **80** | **83,4 %** | **99,5 %** |
| 90 | 82,4 % | 99,5 % |

La marche entre 75 et 80 est nette : en dessous, on rattache des textes
simplement voisins. Le seuil retenu, **88**, est pris au milieu du plateau. On y
perd un sixième des scrutins — perte assumée et chiffrée, préférable à un
sixième de lignes fausses.

Au total : 2 629 scrutins rattachés par lien déclaré, 5 041 par similarité,
**785 non rattachés** (9,3 %), essentiellement des scrutins dont le titre ne
nomme aucun texte (« l'ensemble du texte »).

---

## 3. Rattacher une activité HATVP à un texte de loi (entre bases)

### Première tentative, et son échec

Règle initiale : secteur de l'organisation compatible **et** domaine
d'intervention compatible **et** au moins un mot-clé du texte dans l'objet
déclaré **et** exercice recouvrant la fenêtre de débat. Résultat : 904 activités
retenues pour la loi agricole.

Un échantillon de 60 paires a été relu une à une. Verdict : sur les 25 paires
retenues et tranchables, **4 étaient justes**. Soit une précision d'environ
**16 %**. Les faux positifs sont instructifs — ils viennent presque tous d'un
mot-clé trop général attrapé hors contexte :

> « Contribuer aux réflexions des pouvoirs publics sur l'évolution du cadre
> général des filières de Responsabilité Élargie du Producteur »

retenu pour la loi agricole parce que le mot « filière » y figure. Une variable
d'exposition construite là-dessus aurait été, pour l'essentiel, du bruit.

### Deuxième tentative : deux niveaux assumés

**Niveau 1 — le texte est nommé.** L'objet déclaré contient l'intitulé officiel
normalisé, ou l'une des abréviations d'usage listées dans `config.py` (`LPM`,
`PJL fraude`, `loi d'urgence agricole`…), **en sous-chaîne exacte**.

**Niveau 2 — voisinage thématique.** L'ancienne règle, conservée pour *décrire*
l'écosystème sectoriel qui gravite autour d'un texte, jamais pour affirmer un
ciblage.

Seul le niveau 1 alimente l'analyse.

### Pourquoi aucune similarité floue au niveau 1

Une tentative intermédiaire utilisait `partial_token_set_ratio` entre le titre du
texte et l'objet déclaré, seuil 88. Elle retenait **11 170 activités sur
11 501** — dont des déclarations sur le PLFSS pour la loi agricole. C'est le
comportement attendu de ce scorer : il renvoie 100 dès que les mots de la
référence apparaissent quelque part dans la cible, même dispersés. Le flou est le
bon outil pour comparer *deux titres* (section 2) ; il est le mauvais outil pour
chercher un titre *dans un paragraphe*. Le niveau 1 est donc purement
lexical-exact, au prix d'un rappel faible et assumé.

### Audit du résultat

Échantillon stratifié de 60 paires, 20 par niveau, relues une à une
(`data/processed/audit_ciblage_a_annoter.csv`, colonnes `verdict_manuel` et
`commentaire`). Les paires où le rattachement est plausible mais invérifiable
sont annotées `incertain` et exclues du calcul : les ranger d'un côté ou de
l'autre fabriquerait le résultat.

| Niveau | Paires relues | Vrais ciblages | Incertains | Précision |
| --- | --- | --- | --- | --- |
| 1 — texte nommé | 20 | 20 | 0 | **100 %** |
| 2 — voisinage thématique | 20 | 1 | 4 | **6 %** |
| 0 — écarté | 20 | 0 | 0 | — (aucun faux négatif) |

Sur l'échantillon, le niveau 1 a un **rappel de 95 %** : une seule activité
réellement ciblante lui a échappé, parce qu'elle écrivait « PJL Agricole », forme
absente de la liste d'alias. L'alias a été ajouté ensuite, ce qui a capturé
3 activités supplémentaires, toutes vérifiées manuellement et toutes correctes.
Cette itération est documentée ici plutôt que masquée : le seuil n'a pas été
réglé sur le résultat final, il a été corrigé sur une erreur identifiée.

**Attention à la lecture** : l'échantillon est stratifié, pas aléatoire simple.
Ces précisions valent *par strate* et ne s'extrapolent pas en un taux global.

### Le cas témoin

Le texte `logement` n'est nommé par **aucune** activité du répertoire, alors que
419 activités lui sont thématiquement proches. Si le voisinage thématique
mesurait le ciblage, ce chiffre serait impossible. Il justifie à lui seul
l'exclusion du texte `logement` de la modélisation.

---

## 4. Relier les députés à la HATVP — le contre-exemple utile

Tout n'est pas du rapprochement approximatif. Chaque acteur de l'open data de
l'Assemblée porte un champ `uri_hatvp` qui pointe exactement sur sa page
nominative. **88 % des députés** sont appariés par cette clé exacte, sans aucune
heuristique. Les 12 % restants sont des députés sans déclaration publiée à la
date de collecte, pas des échecs d'appariement.

Le contenu des déclarations (`declarations.xml`) ne porte, lui, pas cette URL :
il faut passer par le nom normalisé, et le taux d'appariement tombe à **78 %**.
La leçon tient en une phrase : *chercher la clé fournie par la source avant
d'inventer la sienne.*

---

## 5. Construire une variable d'exposition qui n'existe pas dans les données

Le répertoire dit « j'ai contacté des députés », jamais « j'ai contacté
M. Untel ». Une exposition individuelle ne peut donc pas être lue ; elle doit
être construite.

**Méthode.** Pour chaque texte, on apprend un espace TF-IDF (unigrammes et
bigrammes, mots vides parlementaires retirés) sur l'union de deux corpus : les
exposés des motifs des amendements de chaque député, et les objets déclarés des
lobbies de niveau 1. On calcule les cosinus, et on retient par député la
proximité maximale et la moyenne des cinq plus proches.

**Ce que ça mesure.** Une convergence de discours. Trois lectures possibles, que
les données ne permettent pas de départager :

1. le lobby a influencé la rédaction de l'amendement ;
2. le lobby a ciblé un député déjà convaincu — c'est la lecture la plus
   fréquente dans la littérature sur le lobbying, et elle suffit à produire la
   corrélation sans aucune influence ;
3. les deux emploient le vocabulaire technique du secteur, sans lien.

Aucune des trois n'est écartée par ce travail. C'est pourquoi le mot
« influence » n'apparaît jamais sans « déclarée » dans les titres de figures.

---

## 6. Trois modèles, dans l'ordre d'un argument

### 6.1 Le vote final : un échec informatif

Logit du vote sur l'ensemble du texte en fonction du bloc politique. Le modèle
**ne converge pas** : la matrice hessienne est singulière, parce que cinq blocs
sur sept votent à 0 % ou 100 %. Ce n'est pas un bug à contourner, c'est le
résultat.

Mesure de substitution, lisible : la règle « chaque député vote comme la majorité
de son bloc » se trompe sur

| Texte | Votes exprimés | Erreurs de la règle | Exactitude |
| --- | --- | --- | --- |
| agriculture | 547 | 3 | 99,5 % |
| defense | 562 | 37 | 93,4 % |
| fraudes | 557 | 3 | 99,5 % |

Il n'y a rien à expliquer de plus au niveau du vote final. Chercher un effet du
lobbying ici reviendrait à chercher de la variance là où il n'y en a pas.

### 6.2 La dissidence : le bon niveau d'observation

Sur les **970 scrutins d'amendements** des trois textes, 4,3 % des 89 472 votes
s'écartent de la position majoritaire du groupe. Logit de cette dissidence,
écarts-types **groupés par député** (un même député apparaît dans des centaines
de scrutins ; des écarts-types classiques seraient artificiellement petits).

Effets marginaux moyens, en points de probabilité :

| Variable | Effet | p |
| --- | --- | --- |
| proximité lexicale avec les lobbies (+1 écart-type) | +0,34 pt | 0,080 |
| intérêt sectoriel déclaré | +0,72 pt | 0,082 |
| a déposé un amendement sur le texte | −1,09 pt | 0,031 |
| ruralité de la circonscription (+1 écart-type) | +0,00 pt | 0,982 |
| membre de la commission saisie au fond | −0,20 pt | 0,494 |

Pseudo-R² = 0,077, n = 87 914, 537 députés.

**Lecture.** Les deux variables liées au lobbying vont dans le sens attendu mais
**ne sont pas significatives au seuil de 5 %**. On ne conclut pas à un effet. On
note que l'ordre de grandeur est faible : +0,34 point sur un taux de base de
4,3 %, soit environ 8 % de hausse relative, pour un écart-type de proximité.
Le seul effet net est négatif et peu surprenant : un député qui dépose des
amendements sur un texte est un député investi dans la ligne de son groupe.

### 6.3 La convergence lexicale : qui parle comme les lobbies ?

Au niveau du député, probabilité d'être au-dessus de la médiane de proximité,
parmi les seuls auteurs d'amendements (166 observations). Aucun coefficient
significatif. Les blocs parfaitement séparants et les modalités de moins de
15 observations sont retirés, et la fonction le journalise explicitement.

---

## 7. Limites, par ordre de gravité

1. **Le répertoire HATVP est autodéclaratif.** Une organisation qui ne déclare
   rien est invisible. Transparency International et l'Observatoire des
   multinationales contestent régulièrement l'exhaustivité du registre et la
   précision des objets déclarés. Ce travail mesure le lobbying *déclaré*, qui
   est un sous-ensemble inconnu du lobbying réel.
2. **Pas de datation fine.** Une activité est rattachée à un exercice annuel. La
   fenêtre de débat est donc élargie de 6 mois de part et d'autre, ce qui est un
   choix arbitraire ; `config.MARGE_FENETRE_MOIS` permet de le faire varier.
3. **Causalité : aucune.** Voir section 5. La corrélation mesurée est compatible
   avec l'absence totale d'influence.
4. **Rappel faible au niveau 1.** Une organisation qui décrit son action sans
   nommer le texte est perdue. Le projet préfère 208 rattachements sûrs à 1 383
   douteux, mais c'est un arbitrage, pas une vérité.
5. **La proximité TF-IDF est lexicale.** Elle ne voit pas que deux formulations
   opposées peuvent partager tout leur vocabulaire : un amendement qui
   *interdit* l'acétamipride et une demande de lobby qui le *réautorise* se
   ressemblent beaucoup pour un cosinus. Un modèle de langue capterait le sens,
   au prix de la reproductibilité et de l'interprétabilité.
6. **Une seule législature.** La XVIIe est marquée par une fragmentation
   politique inhabituelle ; les taux de dissidence ne sont pas transposables.

---

## 8. Référence utile

Regards Citoyens / NosDéputés.fr travaille sur ces données depuis plus de dix
ans. Leurs outils de parsing de l'open data parlementaire ont servi de point de
comparaison pour valider l'ordre de grandeur des volumes extraits ici.

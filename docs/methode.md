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

### Le test placebo

Rien ne garantit a priori que cette mesure capte du *sectoriel* plutôt que du *style*.
On calcule donc, pour chaque amendement, une seconde proximité : celle aux objets
déclarés des lobbies d'un **autre** texte de l'étude (permutation circulaire
agriculture → defense → fraudes → agriculture). Si les deux se valaient, la mesure ne
capterait que « cet amendement est rédigé en français administratif dense ».

Un détail a son importance : les deux corpus sont ramenés à la **même taille** par tirage
à graine fixe. Le maximum d'une similarité sur *N* documents croît mécaniquement avec *N*,
et sans cette correction le témoin « gagnait » sur la défense (14 objets) simplement parce
que son corpus de comparaison en comptait 165.

Résultat : la proximité réelle domine le témoin sur les trois textes (écart des moyennes
de +0,010 à +0,031). La mesure capte bien quelque chose de sectoriel — ce qui ne dit
toujours rien d'une influence.

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

### 6.3 L'adoption des amendements, et ce que le placebo révèle

Unité d'observation : l'amendement. On ne garde que les **1 145** amendements de députés
qui ont été *tranchés* — adoptés ou rejetés. Un amendement retiré, tombé ou non soutenu
n'a pas été jugé sur son contenu, et le compter comme un échec mélangerait deux
phénomènes.

| Mesure | Odds ratio | IC 95 % | p |
| --- | --- | --- | --- |
| proximité aux lobbies du texte | 1,01 | [0,86 ; 1,20] | 0,891 |
| proximité aux lobbies d'un autre texte (témoin) | 0,77 | [0,62 ; 0,95] | **0,015** |

La proximité aux lobbies du texte n'a **aucun effet**. Le témoin, lui, est
significativement **négatif** : un amendement dont le vocabulaire ressemble aux demandes
d'un *autre* secteur a moins de chances d'être adopté.

Sans le placebo, on aurait conclu « pas d'effet » et on serait passé à côté de ce que la
mesure capte réellement : elle sépare les amendements dans le sujet de ceux qui en
sortent, et les amendements hors sujet sont rejetés. Ce qui prédit vraiment l'adoption
reste l'appartenance politique (odds divisés par 3 à droite et par 15 à la gauche
radicale, par rapport au centre).

### 6.4 La convergence lexicale : qui parle comme les lobbies ?

Au niveau du député, probabilité d'être au-dessus de la médiane de proximité,
parmi les seuls auteurs d'amendements (166 observations). Aucun coefficient
significatif. Les blocs parfaitement séparants et les modalités de moins de
15 observations sont retirés, et la fonction le journalise explicitement.

### 6.5 La spécialisation : le seul résultat bien identifié

Toutes les mesures précédentes reposaient sur une inférence. Il existe pourtant une
information **déclarée par le député lui-même** : ses intérêts privés.

Avant de s'en servir, il faut la nettoyer. Première découverte : **51 % de doublons**.
Un député qui dépose une déclaration initiale puis une modificative voit ses intérêts
inchangés recopiés à l'identique ; les compter deux fois aurait gonflé mécaniquement les
députés les plus actifs administrativement. Ensuite, un lexique sectoriel court et lisible
(`features.LEXIQUE_SECTEURS`, 12 secteurs) rattache les libellés à un secteur — **34 %
seulement** : « autoentrepreneur », « SCI familiale » ou « consultant » ne disent rien du
secteur, et ce taux est une limite, pas un détail.

Modèle : probabilité qu'un député dépose au moins un amendement sur un texte, en fonction
de son intérêt déclaré dans le secteur, de son appartenance à la commission saisie au
fond, de la ruralité de sa circonscription et de son bloc (n = 1 639 députés-textes).

| Variable | Odds ratio | p |
| --- | --- | --- |
| intérêt déclaré dans le secteur du texte | **3,01** | 0,0003 |
| membre de la commission saisie au fond | **13,66** | < 0,0001 |
| ruralité de la circonscription (+1 écart-type) | 1,17 | 0,060 |

C'est la seule relation du projet qui n'exige **aucune inférence** : les intérêts sont
déclarés par le député, et le dépôt d'un amendement est un fait. Mais ce n'est pas une
mise en cause. Un ancien agriculteur qui siège en commission des affaires économiques et
amende la loi agricole fait exactement ce pour quoi il a été élu. La frontière entre
**spécialisation** et **conflit d'intérêts** n'est pas dans ces données : elle est dans le
*sens* de l'amendement, que le TF-IDF ne voit pas.

Et l'ampleur de l'effet n'est pas robuste — voir section 9.

---

## 7bis. Les déports : le seul lien nommé

Un **déport** est la décision d'un député de ne pas prendre part à un vote en raison d'un
intérêt personnel. C'est, dans tout le paysage de données exploré ici, **le seul endroit
où un député, un intérêt privé et un texte précis sont nommés ensemble**.

Il y en a **59 depuis 2017**, dont 9 pour la législature en cours. Aucune statistique n'est
possible : c'est une source qualitative, et un point de vérification du reste de la chaîne,
puisque les scrutins étant nominatifs, un déport annoncé est contrôlable ligne à ligne.

Deux limites apparaissent tout de suite :

* la plupart des déports visent **certains articles**, pas le texte entier ; on ne peut
  donc rien conclure au niveau du dossier, le député ayant le droit de voter sur le reste ;
* deux références (« Articles de loi ayant trait aux assurances… ») ne nomment aucun texte
  identifiable et restent volontairement non rattachées.

Un seul déport est vérifiable au niveau du dossier : un député déclarant être « en
disponibilité » d'un groupe industriel de défense, et se déportant de l'intégralité du
projet de loi de programmation militaire. Sur les 292 scrutins du dossier postérieurs à ce
déport, il n'apparaît dans le détail nominatif que pour **un seul vote** — celui sur
l'ensemble du texte issu de la commission mixte paritaire.

Les données disent cela et s'arrêtent là : elles ne disent pas si c'est un oubli, un
changement de situation, ou une lecture du déport qui en exclut le vote final. Ce qu'il
faut en retenir est méthodologique : un engagement public **peut** être vérifié ligne à
ligne dès lors que la source nomme à la fois la personne et le texte. C'est exactement ce
qui manque au répertoire des lobbies.

**Le même piège, une deuxième fois.** La première version du rattachement des déports
utilisait `partial_token_set_ratio` et rattachait les neuf déports de la législature à des
intitulés comme « Allocution du Président d'âge », avec un score de 100. C'est le piège
déjà rencontré au niveau 1 du ciblage HATVP (section 3). Il est maintenant couvert par un
test automatique, pour qu'il ne se reproduise pas une troisième fois.

---

## 8. Contrôles de qualité

Une erreur de parsing produit une exception, qu'on voit. Une erreur de données produit un
tableau plausible et faux, qu'on ne voit pas. Le module `quality.py` écrit noir sur blanc
ce qu'on attend des tables et vérifie que c'est vrai : **24 contrôles**, tous au vert.

Une première version en signalait trois en rouge. Les trois se sont révélées être des
régularités explicables — et c'est pour ça que ce sont devenus des contrôles *précis*
plutôt que des seuils génériques de complétude :

| Anomalie apparente | Explication trouvée |
| --- | --- |
| 44,5 % des amendements sans `sort` | un amendement n'a de sort que s'il a été *discuté* : la relation est exacte, pas approximative |
| 1,1 % des amendements sans auteur | ce sont exactement les amendements du **Gouvernement**, qui n'a pas d'auteur député |
| 12 scrutins pointant vers un dossier introuvable | leurs identifiants commencent tous par `DLR5L16` : textes entamés sous la XVIe législature |

Quatre lignes résistaient encore à la deuxième explication : des amendements à l'état
« effacé », dont l'auteur a été retiré en même temps que le contenu. Quatre sur 126 392 —
mais quatre lignes inexpliquées suffisent à faire douter du reste, donc elles sont tracées
et exclues explicitement plutôt que tolérées en silence.

Chaque contrôle est testé contre une anomalie fabriquée exprès : un contrôle qui ne sait
pas détecter un défaut volontaire ne détectera pas non plus les vrais.

---

## 9. Robustesse : ce qui se passe quand on change les choix arbitraires

Trois choix n'ont aucune justification théorique et ont été faits à la main. Un résultat
qui dépend de l'un d'eux n'est pas un résultat.

### Largeur de la fenêtre temporelle

| Marge | Activités de niveau 1 | Coefficient de proximité | p |
| --- | --- | --- | --- |
| ± 0 mois | 184 | 0,065 | 0,102 |
| ± 3 mois | 187 | 0,069 | 0,103 |
| **± 6 mois** (retenu) | **208** | **0,086** | **0,081** |
| ± 12 mois | 209 | 0,086 | 0,081 |
| ± 24 mois | 256 | 0,081 | 0,133 |

Le volume retenu varie de 184 à 256 ; le coefficient reste entre 0,06 et 0,09 et n'atteint
jamais le seuil de 5 %. Le non-résultat de la section 6.2 n'est pas un artefact de ce choix.

### Façon de résumer la proximité, et de repérer un intérêt

| Variante | Odds ratio | p |
| --- | --- | --- |
| proximité = maximum | 1,09 | 0,081 |
| proximité = moyenne des 5 plus proches | 1,07 | 0,236 |
| intérêt = vocabulaire du texte | 3,01 | 0,0003 |
| intérêt = classement sectoriel | 1,70 | 0,054 |

**Ce point tempère sérieusement le résultat de la section 6.5.** Les deux repérages de
l'intérêt sectoriel s'accordent à 93 % — mais sur une variable aussi rare, l'accord brut
est trompeur : le **kappa de Cohen vaut 0,45**, soit un accord seulement modéré. L'effet
reste positif et de même sens, mais son ampleur passe d'un odds ratio de 3,0 à 1,7 et sa
p-value de 0,0003 à 0,054.

Conclusion honnête : *le sens de la relation est robuste, son ampleur ne l'est pas.* Mieux
vaut annoncer le bas de la fourchette.

### Déterminisme

Deux sources d'aléa existent : le tirage de l'échantillon d'audit et le
sous-échantillonnage du corpus placebo. Les deux sont à graine fixe — encore faut-il le
vérifier, parce qu'une graine oubliée ne se voit jamais sur une seule exécution. Le
pipeline recalcule trois tables deux fois de suite et compare leurs empreintes SHA-256.

---

## 10. Limites, par ordre de gravité

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

## 11. Référence utile

Regards Citoyens / NosDéputés.fr travaille sur ces données depuis plus de dix
ans. Leurs outils de parsing de l'open data parlementaire ont servi de point de
comparaison pour valider l'ordre de grandeur des volumes extraits ici.

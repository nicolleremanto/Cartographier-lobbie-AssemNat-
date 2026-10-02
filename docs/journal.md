# Journal de travail

À tenir au fil du projet : c'est ce qui permet, à la soutenance, de répondre à
« pourquoi avez-vous fait ce choix ? » autrement que par « ça marchait mieux ».

## 2 octobre 2026 — mise en place et première chaîne complète

**Fait**

* Vérification de la faisabilité sur échantillon : les trois bases ont bien le
  volume annoncé (1,27 M de votes, 126 k amendements, 113 k activités HATVP).
* Repérage des clés de jointure réellement disponibles. Découverte importante :
  le champ `uri_hatvp` des acteurs de l'Assemblée pointe exactement sur la fiche
  HATVP du député — une clé exacte offerte par la source, là où on s'attendait à
  devoir rapprocher des noms.
* Quatrième source ajoutée (API Géo) pour construire un indicateur rural/urbain.
* Chaîne complète écrite et exécutée : collecte → parsing → matching → variables
  → modèles → figures.
* 32 tests, centrés sur le matching et les cas limites du JSON de l'Assemblée.

**Décisions, et ce qui les a motivées**

| Décision | Raison |
| --- | --- |
| Arbitrer les candidats de matching par la date du scrutin | précision passée de 95,7 % à 99,5 % ; les dossiers homonymes (une entrée par lecture) étaient la seule source d'erreur résiduelle |
| Abandonner la règle de ciblage thématique comme variable d'analyse | audit manuel : ~16 % de précision, les faux positifs venant de mots-clés généraux (« filière ») |
| Refuser toute similarité floue pour le ciblage HATVP | `partial_token_set_ratio` retenait 11 170 activités sur 11 501, PLFSS compris |
| Modéliser la dissidence plutôt que le vote final | le vote final est prédit à 93-99 % par le bloc : plus aucune variance à expliquer |
| Garder le texte `logement` sans l'analyser | 419 activités thématiquement proches, zéro qui le nomme : le meilleur cas témoin disponible |

**Erreurs commises, et comment elles ont été vues**

* Une définition de fonction dupliquée dans `matching.py` faisait silencieusement
  gagner l'ancienne version : les compteurs de ciblage restaient identiques
  après correction. Repéré en comparant les volumes entre deux exécutions.
* Première version du graphe biparti illisible (600 nœuds, étiquettes
  superposées). Corrigé par un seuil de degré adaptatif et un liseré blanc.
* Titre de figure affirmant une différence entre blocs que la figure ne montrait
  pas. Titre corrigé plutôt que figure forcée.

---

## 2 octobre 2026 (suite) — consolidation

**Fait**

* **Volet amendements** : nouvelle unité d'analyse (2 452 amendements de députés sur les
  trois textes), avec un **test placebo** — proximité aux lobbies d'un *autre* texte, sur
  un corpus ramené à la même taille. C'est lui qui a révélé ce que la mesure capte
  vraiment.
* **Volet intérêts déclarés** : dédoublonnage (51 % de doublons dus aux déclarations
  modificatives), classement sectoriel par lexique, et le seul résultat bien identifié du
  projet.
* **Déports** : 59 déclarations de conflit d'intérêts, le seul endroit où un député, un
  intérêt et un texte sont nommés ensemble. Rattachés aux dossiers et vérifiés contre les
  scrutins.
* **`quality.py`** : 24 contrôles de qualité des données, chacun testé contre une anomalie
  fabriquée exprès.
* **`robustesse.py`** : sensibilité à la fenêtre temporelle, à la mesure de proximité et à
  la mesure d'intérêt ; vérification du déterminisme par empreintes SHA-256.
* Makefile, intégration continue GitHub Actions, 58 tests.

**Décisions**

| Décision | Raison |
| --- | --- |
| Ramener les corpus placebo à la même taille | le maximum d'une similarité sur *N* documents croît avec *N* : sans ça le témoin « gagnait » sur la défense |
| Ne conserver que les paires éligibles dans `ciblage_hatvp` | le produit cartésien complet faisait 452 000 lignes et 42 Mo, pour aucune information de plus |
| Seuil de 0,05 pour les arêtes du graphe | choix de lisibilité, assumé comme tel : au-dessus le graphe de la défense tombait à une arête |
| Annoncer le bas de la fourchette pour l'effet des intérêts déclarés | kappa de 0,45 entre les deux mesures : le sens est robuste, l'ampleur non |

**Erreurs commises, et comment elles ont été vues**

* `partial_token_set_ratio` utilisé une **deuxième** fois, sur les déports : il rattachait
  les neuf déports de la législature à « Allocution du Président d'âge » avec un score de
  100. Repéré en lisant le tableau de sortie, pas en lisant le code. Désormais couvert par
  un test.
* Le filtre de longueur sur les titres de dossiers (`> 10` caractères) excluait
  « Fin de vie ». Abaissé à 5 après vérification que cela ne change ni la couverture ni la
  précision du rattachement des scrutins.
* Première version des contrôles qualité trop générique : trois « échecs » qui étaient en
  fait des régularités de la source. Un contrôle qui crie au loup est pire que pas de
  contrôle.

**À faire ensuite**

- [ ] Faire valider le sujet par la chargée de TD.
- [ ] Créer le dépôt GitHub public et pousser **progressivement** : l'historique
      de version est noté, un dépôt constitué d'un seul envoi est pénalisé.
- [ ] Confirmer les dates exactes de rendu et de soutenance.
- [ ] Volet pantouflage : les 11 438 intérêts déclarés par les députés sont déjà
      chargés (`hatvp_interets_deputes`) mais pas encore exploités. Croiser les
      reconversions de fin de mandat avec les votes sur les textes du secteur
      concerné.
- [ ] Étendre aux textes budgétaires (PLF, PLFSS), où le lobbying déclaré est de
      loin le plus dense — et où le rattachement scrutin → dossier est le plus
      difficile.
- [ ] Tester une mesure de proximité sémantique (embeddings de phrases) contre
      le TF-IDF, qui ne distingue pas deux positions opposées sur le même sujet.

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

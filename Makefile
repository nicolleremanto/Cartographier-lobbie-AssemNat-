# Raccourcis du projet. « make » seul affiche l'aide.
.DEFAULT_GOAL := aide
.PHONY: aide installation donnees pipeline rapide qualite tests rapport figures propre tout

PYTHON ?= python
PIPELINE := $(PYTHON) -m lobbynomics.pipeline

aide:                     ## affiche cette aide
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	 awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-12s\033[0m %s\n", $$1, $$2}'

installation:             ## installe les dépendances
	$(PYTHON) -m pip install -r requirements.txt

donnees:                  ## télécharge et décompresse les sources officielles (~700 Mo)
	$(PIPELINE) --etapes collecte parsing

pipeline:                 ## chaîne complète, de l'URL aux figures
	$(PIPELINE) --strict

rapide:                   ## rejoue tout sauf la collecte et le parsing
	$(PIPELINE) --etapes matching features qualite modeles robustesse figures --strict

qualite:                  ## contrôles de qualité des tables
	$(PIPELINE) --etapes qualite --strict

figures:                  ## régénère uniquement les figures
	$(PIPELINE) --etapes figures

tests:                    ## suite de tests
	$(PYTHON) -m pytest -q

rapport:                  ## exécute le notebook de bout en bout (vérifie la reproductibilité)
	jupyter nbconvert --to notebook --execute --inplace notebooks/rapport.ipynb \
	  --ExecutePreprocessor.timeout=900

propre:                   ## supprime les tables dérivées (les sources brutes sont conservées)
	rm -rf data/processed data/interim reports/figures
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

tout: installation pipeline tests rapport   ## installation, pipeline, tests et rapport

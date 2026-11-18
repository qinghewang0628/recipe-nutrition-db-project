# DSC5003 Group Project - Person A (Data Engineering)
# One-command rebuild: `make seed` (or `python make.py seed` on any platform).
# Requires Python 3.9+ only; no third-party packages.
PYTHON ?= python

.PHONY: help seed all mappings dictionary profile clean-data scale seed-sql load test verify demo pack unpack

help:
	@echo "make seed        Full rebuild (profile -> clean -> scales -> SQL -> verify)"
	@echo "make profile     Rebuild the profile and metrics only"
	@echo "make dictionary  Rebuild the column dictionary only"
	@echo "make clean-data  Run the cleaner only -> data/clean/"
	@echo "make scale       Rebuild the three scale tiers (FACTORS=1,5,10 supported)"
	@echo "make seed-sql    Rebuild sql/load_*.sql and data/manifest.json"
	@echo "make load        Load into PostgreSQL (needs DATABASE_URL and schema.sql)"
	@echo "make test        Unit tests + correctness verification"
	@echo "make verify      Correctness verification only"
	@echo "make demo        Print the before/after figures used in the video"
	@echo "make pack        Compress scale CSVs above 50 MB to .csv.gz"
	@echo "make unpack      Restore from .csv.gz"
	@echo "make help        Show this help"

seed all:
	$(PYTHON) -m etl.pipeline all

mappings:
	$(PYTHON) -m etl.pipeline mappings

dictionary:
	$(PYTHON) -m etl.pipeline dictionary

profile:
	$(PYTHON) -m etl.pipeline profile

clean-data:
	$(PYTHON) -m etl.pipeline clean

scale:
ifdef FACTORS
	$(PYTHON) -m etl.pipeline scale --factors $(FACTORS)
else
	$(PYTHON) -m etl.pipeline scale
endif

seed-sql:
	$(PYTHON) -m etl.pipeline seed

load:
	@test -n "$(DATABASE_URL)" || { echo "Set DATABASE_URL, e.g. make load DATABASE_URL=postgres://user:pwd@localhost:5432/recipes"; exit 1; }
	psql "$(DATABASE_URL)" -f sql/load_clean.sql

verify:
	$(PYTHON) -m etl.pipeline verify

test:
	$(PYTHON) -m unittest discover -s tests -v
	$(PYTHON) -m etl.pipeline verify

demo:
	$(PYTHON) -m etl.pipeline demo

pack:
	$(PYTHON) -m etl.pipeline pack

unpack:
	$(PYTHON) -m etl.pipeline unpack

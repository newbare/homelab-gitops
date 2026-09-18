VENV := .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip
USERS ?= data/users.csv

.PHONY: venv install dry-run run clean test

venv:
	python3 -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

dry-run: install
	$(PY) -m src.cli --users $(USERS) --dry-run

run: install
	$(PY) -m src.cli --users $(USERS) --workers 8

test: install
	$(PY) -m pytest tests/ -v

clean:
	rm -rf $(VENV) __pycache__ src/__pycache__ tests/__pycache__ .pytest_cache

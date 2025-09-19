.ONESHELL:

install:
	python -m venv .venv
	. .venv/bin/activate; python -m pip install --upgrade pip; pip install -r requirements.txt

fetch:
	. .venv/bin/activate; python -m app.etl.nyc_fetch all

normalize:
	. .venv/bin/activate; python -m app.etl.nyc_normalize

test:
	. .venv/bin/activate; python -m pytest -q

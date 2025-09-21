.ONESHELL:

install:
	python -m venv .venv
	. .venv/bin/activate; python -m pip install --upgrade pip; pip install -r requirements.txt

fetch:
	. .venv/bin/activate; python -m app.etl.nyc_fetch all

normalize:
	. .venv/bin/activate; python -m app.etl.nyc_normalize


serve:
	. .venv/bin/activate; uvicorn app.api.main:app --reload --port 8000

openapi:
	. .venv/bin/activate; python scripts/export_openapi.py

accept:
	. .venv/bin/activate; python scripts/acceptance.py run --base-url http://127.0.0.1:8000


test:
	. .venv/bin/activate; python -m pytest -q

.ONESHELL:

install:
	python -m venv .venv
	. .venv/bin/activate; python -m pip install --upgrade pip; pip install -r requirements.txt

fetch:
	. .venv/bin/activate; python -m app.etl.de_boris_fetch current

normalize:
	. .venv/bin/activate; python -m app.etl.de_boris_normalize

serve:
	. .venv/bin/activate; uvicorn app.api.main:app --reload --port 8000

openapi:
	. .venv/bin/activate; python -m scripts.export_openapi

accept:
	. .venv/bin/activate; python -m scripts.acceptance --base-url http://127.0.0.1:8000

test:
	. .venv/bin/activate; python -m pytest -q

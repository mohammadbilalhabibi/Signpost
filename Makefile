PYTHON ?= python
PORT ?= 7860

.PHONY: install ingest index reranker serve eval test lint format

install:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

ingest:
	$(PYTHON) scripts/ingest.py

index:
	$(PYTHON) scripts/build_index.py

reranker:
	$(PYTHON) -m pip install -e ".[export]"
	$(PYTHON) scripts/export_reranker.py

serve:
	$(PYTHON) -m uvicorn app.api:app --host 0.0.0.0 --port $(PORT) --reload

eval:
	$(PYTHON) eval/run_eval.py

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

format:
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check --fix .

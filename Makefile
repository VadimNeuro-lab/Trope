.PHONY: install test lint smoke assets clean

install:
	python -m pip install -e ".[dev,analysis]"

test:
	python -m pytest -q

lint:
	python -m ruff check src tests scripts

smoke:
	bash scripts/smoke.sh

assets:
	python scripts/build_assets.py --encoder tfidf

clean:
	rm -rf .pytest_cache .ruff_cache **/__pycache__ build dist *.egg-info

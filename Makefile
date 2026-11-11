PYTHON ?= python3
PORT ?= 8000

.DEFAULT_GOAL := site

.PHONY: site content dev legacy install clean

## Build the whole site into dist/
site:
	$(PYTHON) frontend/build.py

## Compile the LaTeX sources only, no shell rendering
content:
	$(PYTHON) frontend/build.py --content-only

## Build the site and serve it locally
dev: site
	@echo "Serving dist/ on http://localhost:$(PORT)/"
	$(PYTHON) -m http.server $(PORT) --directory dist

## Build the old site (kept for reference) into legacy/_site/
legacy:
	$(PYTHON) legacy/build.py

## Install the frontend dependencies
install:
	$(PYTHON) -m pip install -r frontend/requirements.txt

## Remove every build artifact
clean:
	rm -rf .build dist frontend/public/generated legacy/_site

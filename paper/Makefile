LATEXMK = latexmk -pdf -interaction=nonstopmode -halt-on-error

all: arxiv.pdf

# The arXiv preprint (the paper). The retired POPL'27 submission flow
# (main.tex, the standalone appendix, the anonymized artifact) lives at
# tags popl27-submitted / popl27-snapshot.*.
arxiv.pdf: arxiv.tex macros.tex sections/*.tex results/tables/*.tex \
		appendix/body-arxiv.tex
	$(LATEXMK) arxiv.tex

# Ready-to-upload arXiv source bundle (arXiv runs LaTeX but not BibTeX,
# so the .bbl ships instead of references.bib). The tarball is tracked
# (dist/); the staging dir (dist/arxiv-src/) is regenerable and ignored.
arxiv-dist: arxiv.pdf
	rm -rf dist/arxiv-src
	mkdir -p dist/arxiv-src/sections dist/arxiv-src/results/tables \
		dist/arxiv-src/appendix
	cp arxiv.tex arxiv.bbl macros.tex dist/arxiv-src/
	cp sections/*.tex dist/arxiv-src/sections/
	cp results/tables/*.tex dist/arxiv-src/results/tables/
	cp appendix/body-arxiv.tex dist/arxiv-src/appendix/
	tar -czf dist/hurdy-gurdy-arxiv-src.tar.gz -C dist/arxiv-src .
	@echo "arXiv source bundle: dist/hurdy-gurdy-arxiv-src.tar.gz"

results:
	python3 results/harvest.py

clean:
	latexmk -C arxiv.tex
	rm -f arxiv.bbl

.PHONY: all arxiv-dist results clean

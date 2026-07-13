LATEXMK = latexmk -pdf -interaction=nonstopmode -halt-on-error

all: main.pdf appendix/appendix.pdf arxiv.pdf

main.pdf: main.tex macros.tex sections/*.tex results/tables/*.tex
	$(LATEXMK) main.tex
	python3 check_crosswalk.py

# The supplementary appendix is a standalone document shipped in the
# artifact (POPL'27 call: appendices move to supplementary material).
appendix/appendix.pdf: appendix/appendix.tex appendix/body.tex macros.tex
	cd appendix && $(LATEXMK) appendix.tex

# arXiv preprint: de-anonymized single author, funding acks, appendix
# inline. Excluded from the anonymized artifact. Since the v2 restructure
# it forks the calculus section (sections/calculus-arxiv.tex) and the
# appendix body (appendix/body-arxiv.tex); the unforked files stay frozen
# for the POPL flow.
arxiv.pdf: arxiv.tex macros.tex sections/*.tex results/tables/*.tex \
		appendix/body-arxiv.tex
	$(LATEXMK) arxiv.tex

# Ready-to-upload arXiv source bundle (arXiv runs LaTeX but not BibTeX,
# so the .bbl ships instead of references.bib).
arxiv-dist: arxiv.pdf
	rm -rf ../dist/arxiv-src
	mkdir -p ../dist/arxiv-src/sections ../dist/arxiv-src/results/tables \
		../dist/arxiv-src/appendix
	cp arxiv.tex arxiv.bbl macros.tex ../dist/arxiv-src/
	cp sections/*.tex ../dist/arxiv-src/sections/
	cp results/tables/*.tex ../dist/arxiv-src/results/tables/
	cp appendix/body-arxiv.tex ../dist/arxiv-src/appendix/
	tar -czf ../dist/hurdy-gurdy-arxiv-src.tar.gz -C ../dist/arxiv-src .
	@echo "arXiv source bundle: ../dist/hurdy-gurdy-arxiv-src.tar.gz"

results:
	python3 results/harvest.py

clean:
	latexmk -C main.tex
	latexmk -C arxiv.tex
	cd appendix && latexmk -C appendix.tex
	rm -f main.bbl arxiv.bbl

.PHONY: all arxiv-dist results clean

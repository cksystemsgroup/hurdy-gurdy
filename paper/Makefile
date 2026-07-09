LATEXMK = latexmk -pdf -interaction=nonstopmode -halt-on-error

all: main.pdf appendix/appendix.pdf

main.pdf: main.tex macros.tex sections/*.tex results/tables/*.tex
	$(LATEXMK) main.tex

# The supplementary appendix is a standalone document shipped in the
# artifact (POPL'27 call: appendices move to supplementary material).
appendix/appendix.pdf: appendix/appendix.tex macros.tex
	cd appendix && $(LATEXMK) appendix.tex

results:
	python3 results/harvest.py

clean:
	latexmk -C main.tex
	cd appendix && latexmk -C appendix.tex
	rm -f main.bbl

.PHONY: all results clean

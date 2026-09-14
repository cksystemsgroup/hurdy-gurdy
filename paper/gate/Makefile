# The sixth-generation paper. `make` builds gate.pdf via latexmk
# (pdflatex + bibtex). Shares only ../references.bib with the other
# papers in this directory; the preamble is from scratch. `make clean`
# removes the build products and keeps gate.pdf.
all:
	latexmk -pdf -bibtex gate.tex

clean:
	latexmk -c gate.tex
	rm -f gate.bbl

.PHONY: all clean

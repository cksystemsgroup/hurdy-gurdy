LATEXMK = latexmk -pdf -interaction=nonstopmode -halt-on-error

all: main.pdf

main.pdf: main.tex sections/*.tex results/tables/*.tex
	$(LATEXMK) main.tex

results:
	python3 results/harvest.py

clean:
	latexmk -C main.tex
	rm -f main.bbl

.PHONY: all results clean

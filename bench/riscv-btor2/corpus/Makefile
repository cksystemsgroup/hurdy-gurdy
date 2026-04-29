# Build source.elf and pcs.json for every task in the corpus.
#
# Usage:
#   make                          # build everything
#   make 0001-x0-write-dropped    # build one task by slug
#   make clean                    # remove generated artifacts
#
# Requires the bare-metal RV64 toolchain in PATH (shipped in
# christophkirsch/hurdy-gurdy-bench:latest):
#   riscv64-unknown-elf-as / -ld
#
# pcs.json is emitted by _emit_pcs.py via the riscv-btor2 pair's own
# ELF reader. Task authors look up PCs in pcs.json instead of hand-
# counting bytes (which is wrong as soon as the assembler picks RVC).

# NB: use := (immediate). `?=` does NOT override make's built-in AS=as.
AS        := riscv64-unknown-elf-as
LD        := riscv64-unknown-elf-ld
# -g: GAS emits .debug_line entries automatically per source line.
# _emit_dwarfmap.py reshapes them into the sidecar JSON the pair's
# loader picks up; lift then populates file/line on every step.
ASFLAGS   := -march=rv64imc -mabi=lp64 -g
LDFLAGS   := -Ttext=0x10000 --no-relax
REPO_ROOT := $(abspath $(CURDIR)/../../..)

TASKS := $(notdir $(patsubst %/source.S,%,$(wildcard */source.S)))

.PHONY: all clean $(TASKS)

all: $(addsuffix /source.elf,$(TASKS)) $(addsuffix /pcs.json,$(TASKS)) $(addsuffix /source.elf.dwarfmap.json,$(TASKS))

# `make <slug>` builds one task end-to-end.
$(TASKS): %: %/source.elf %/pcs.json %/source.elf.dwarfmap.json

%/source.elf: %/source.S
	$(AS) $(ASFLAGS) -o $*/source.o $<
	$(LD) $(LDFLAGS) -o $@ $*/source.o
	rm $*/source.o

%/pcs.json: %/source.elf _emit_pcs.py
	PYTHONPATH=$(REPO_ROOT) python $(CURDIR)/_emit_pcs.py $<

%/source.elf.dwarfmap.json: %/source.elf _emit_dwarfmap.py
	python $(CURDIR)/_emit_dwarfmap.py $<

clean:
	rm -f $(addsuffix /source.elf,$(TASKS))
	rm -f $(addsuffix /pcs.json,$(TASKS))
	rm -f $(addsuffix /source.elf.dwarfmap.json,$(TASKS))

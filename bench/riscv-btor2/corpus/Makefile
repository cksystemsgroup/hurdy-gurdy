# Build source.elf for every task in the corpus.
#
# Usage:
#   make            # build all tasks
#   make 0001-x0-write-dropped   # build one task by slug
#   make clean      # remove every source.elf
#
# Requires a bare-metal RV64 toolchain in PATH:
#   riscv64-unknown-elf-as  (assembler)
#   riscv64-unknown-elf-ld  (linker)
#
# A future Dockerfile change will install these in the bench image so
# the build is reproducible there. Until then, install locally:
#   - macOS:  brew install riscv-gnu-toolchain
#   - Debian: apt-get install gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf

AS      ?= riscv64-unknown-elf-as
LD      ?= riscv64-unknown-elf-ld
ASFLAGS ?= -march=rv64imc -mabi=lp64
LDFLAGS ?= -Ttext=0x10000 --no-relax

TASKS := $(notdir $(patsubst %/source.S,%,$(wildcard */source.S)))

.PHONY: all clean $(TASKS)

all: $(addsuffix /source.elf,$(TASKS))

$(TASKS): %: %/source.elf

%/source.elf: %/source.S
	$(AS) $(ASFLAGS) -o $*/source.o $<
	$(LD) $(LDFLAGS) -o $@ $*/source.o
	rm $*/source.o

clean:
	rm -f $(addsuffix /source.elf,$(TASKS))

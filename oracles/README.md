# oracles — outside the executable surface

```
bench/   the pinned image of the tools that testify at admission and
         never run in a play (DOCKER.md there; record its digest)
packs/   recorded testimony: languages/<L>/vectors, pairs/<P>/corpus,
         engines/<P>/corpus with the engine's labels — each with a
         PROVENANCE.md naming the tag, the entry, and what produced it
```

Nothing under this directory is imported, invoked, or routed by the
kernel (`KERNEL.md` §6, §10). An oracle testifies from outside: its
output enters the registry only as anchors with provenance, it never
joins the trusted base, and a disagreement with a generated judge is
a dispute to record and adjudicate, never a verdict.

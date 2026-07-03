import Calculus.Pasting
import Calculus.Fidelity
import Calculus.EndToEnd
import Calculus.Ratchet
import Calculus.Telescope

/-!
# Axiom audit

Printed at build time so every `lake build` re-establishes the
footprint. Expected: `disagreement_localizes`,
`agreement_corroborates`, `existential_self_certifying`, and the two
ratchet theorems are axiom-free; `pasting`, `pasting₃`,
`weakest_link_universal`, `reestablishment`, and
`universal_needs_machinery` use only `propext`; `localization` is the
one classical proof (`Classical.choice`, via its case split) — exactly
the paper's remark that an unfaithful route names no witness by itself.
-/

open Calculus

#print axioms pasting
#print axioms pasting₃
#print axioms localization
#print axioms weakest_link_universal
#print axioms reestablishment
#print axioms kfaithful_of_faithful
#print axioms disagreement_localizes
#print axioms agreement_corroborates
#print axioms existential_self_certifying
#print axioms universal_needs_machinery
#print axioms ratchet_preserves_faithful
#print axioms ratchet_coverage_mono
#print axioms Route.route_pasting
#print axioms Route.route_localization
#print axioms faithful_reproject

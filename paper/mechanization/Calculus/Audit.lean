import Calculus.Pasting
import Calculus.Fidelity
import Calculus.EndToEnd
import Calculus.Ratchet
import Calculus.Telescope
import Calculus.Specialization
import Calculus.Lax
import Calculus.Contract
import Calculus.Frontier

/-!
# Axiom audit

Printed at build time so every `lake build` re-establishes the
footprint. Expected: `disagreement_localizes`,
`agreement_corroborates`, `existential_self_certifying`, and the two
ratchet theorems are axiom-free; `pasting`, `pasting₃`,
`weakest_link_universal`, `reestablishment`, and
`universal_needs_machinery` and `universal_from_open_artifact` use only `propext`; `localization` is the
one classical proof (`Classical.choice`, via its case split) — exactly
the paper's remark that an unfaithful route names no witness by itself.
The lax extension adds no axioms beyond the same footprint:
`laxFaithful_of_faithful` is axiom-free; `lax_pasting`,
`DRoute.direction_exact_iff`, and `lax_universal_transfer` use only
`propext`; the telescoped `DRoute.lax_route_pasting` adds `Quot.sound`
(structural-recursion equations), as `Route.route_pasting` does.
The frontier model (`Frontier.lean`) keeps the footprint:
`answerable_mono` and `lifecycle_ratchet` are axiom-free; the
diagnosis-order and plan lemmas use `propext`/`Quot.sound` (omega's
arithmetic certificates); `diagnosis_total`, the chain lemma
`adequate_chain_answerable`, and the F5 fixpoint
`saturation_terminates` are the model's classical trio
(`Classical.choice`, via boundary-crossing / by-contradiction) —
exactly the remark that an unanswerable question does not name its
failing condition constructively; the platform's `why_not` and
`gurdy saturation` compute the diagnosis and the emptiness check
because the five conditions and the demand list are decidable there.
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
#print axioms universal_from_open_artifact
#print axioms laxFaithful_of_faithful
#print axioms laxFaithful_id_iff_faithful
#print axioms lax_pasting
#print axioms DRoute.lax_route_pasting
#print axioms DRoute.direction_exact_iff
#print axioms lax_universal_transfer
#print axioms Direction.comp_eq_min
#print axioms Contract.comp_glb
#print axioms Frontier.answerable_mono
#print axioms Frontier.diagnosis_total
#print axioms Frontier.diagnosis_unique
#print axioms Frontier.diagnosis_progress
#print axioms Frontier.diagnosis_strict_progress
#print axioms Frontier.adequate_chain_answerable
#print axioms Frontier.saturation_terminates
#print axioms Frontier.lifecycle_ratchet
#print axioms Contract.comp_mono
#print axioms Frontier.conditional_plan_sound

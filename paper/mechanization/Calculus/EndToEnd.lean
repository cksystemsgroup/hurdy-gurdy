import Calculus.Fidelity

/-!
# The end-to-end guarantee

§4.6 of the paper: the existential/universal asymmetry
(Theorems 4.8 and 4.9). `sem` is the reference semantics `⟦·⟧`;
interpreter adequacy (Assumption 1) appears as an explicit hypothesis,
never as an axiom — the hypothesis list of each theorem *is* its
trusted computing base, which is the ledger of §4.4 made literal:

* `existential_self_certifying` assumes adequacy of the **source
  interpreter only**. No translator, carry-back, hub interpreter, or
  solver appears among its hypotheses at all — they are discovery
  devices, incapable of making the conclusion false.
* `universal_needs_machinery` additionally assumes route faithfulness
  at every instance (the universal-class evidence, or per-run evidence
  plus branch agreement), the certified target-side verdict, and the
  correspondence of the asked condition through the keep-projection —
  exactly clauses (i)–(iii) of Theorem 4.9.
-/

namespace Calculus

/-- **Theorem 4.8 (Existential answers are self-certifying).** If the
replay of a carried-back witness exhibits `φ` under `I_A`, then `φ`
truly holds of `⟦p₀⟧` — with interpreter adequacy as the *only*
assumption about any component. The proof term is three tokens long;
that is the theorem's content. -/
theorem existential_self_certifying
    {A : Language} {γ : Type} {sem IA : Interp A} {π : A.Obs → γ}
    (adequacy : ∀ p b, IA p = some b → sem p = some b)
    {φ : Beh γ → Prop} {p₀ : A.Prog} {b : Beh A.Obs}
    (hreplay : IA p₀ = some b)
    (hφ : φ (projB π b)) :
    ∃ b', sem p₀ = some b' ∧ φ (projB π b') :=
  ⟨b, adequacy _ _ hreplay, hφ⟩

/-- **Theorem 4.9 (Universal answers need the machinery).** For an open
program family `p : X → A.Prog` (inputs folded into programs), if
(definedness) the route and the source interpreter are total on the
family, (i) the route is faithful at every instance, (ii) `K` is the
kept projection and `φ` transports through the carry-back to the
target-side `φZ`, and (iii) the certified solver verdict excludes `φZ`
on every target behavior, then no instance's reference behavior
satisfies `φ` — up to the declared loss (`φ` reads only `K`). -/
theorem universal_needs_machinery
    {A Z : Language} {γᵣ κ : Type} {X : Type}
    {sem IA : Interp A} {IZ : Interp Z} {R : Pair A Z γᵣ}
    {p : X → A.Prog} {K : A.Obs → κ}
    (hK : Factors K R.π)
    (adequacy : ∀ q b, IA q = some b → sem q = some b)
    {φ : Beh κ → Prop} {φZ : Beh Z.Obs → Prop}
    (hrun : ∀ x, ∃ z bZ r, R.T (p x) = some z ∧ IZ z = some bZ ∧
      R.carry bZ = some r)
    (hIA : ∀ x, ∃ b, IA (p x) = some b)
    (hfaith : ∀ x, FaithfulAt IA IZ R (p x))
    (hcorr : ∀ bZ r, R.carry bZ = some r → φ (projB K r) → φZ bZ)
    (hZ : ∀ x z bZ, R.T (p x) = some z → IZ z = some bZ → ¬ φZ bZ) :
    ∀ x b, sem (p x) = some b → ¬ φ (projB K b) := by
  intro x b hsem hφ
  obtain ⟨z, bZ, r, hT, hIZ, hΛ⟩ := hrun x
  obtain ⟨b₀, hb₀⟩ := hIA x
  -- The reference behavior is the interpreter's (adequacy + determinism).
  have hsem₀ : sem (p x) = some b₀ := adequacy _ _ hb₀
  have hb : b = b₀ := by
    rw [hsem] at hsem₀
    exact Option.some.inj hsem₀
  subst hb
  -- Route faithfulness at this instance, restricted to K.
  have hf : projB K b = projB K r := hK.congrB (hfaith x hT hb₀ hIZ hΛ)
  -- Transport φ to the target side and contradict the certified verdict.
  exact hZ x z bZ hT hIZ (hcorr bZ r hΛ (hf ▸ hφ))

end Calculus

# Saturation report — `hwmcc-sosylab-beem`

Source: `github:CyanoKobalamyne/hwmcc-benchmarks@57174f5d6f575aedcfe83694b35ec8e7b83043fc` (110 questions, sha256-pinned). Caps: `{"abc_wall_s": 600, "already_spent_modes": ["ind", "ic3bits", "mbic3", "dar", "interp", "ismc", "ic3ia", "ic3sa", "sygus-pdr", "avr"], "decide_wall_s": 300, "engine": "native+residue", "k": 20, "pono_msat_image": "pono-msat:c81aa36", "pono_msat_wall_s": 600, "portfolio": ["msat-ic3ia", "abc-pdr"], "probe": "bounded BMC at the probe bound", "probe_ks": [2, 4, 8]}` — capped results are capped, never full-suite.

**Saturated: False**

## The curve

| iteration | solved | open | answered | saturated |
|---|---|---|---|---|
| 0 | 79 | 31 | 0.7182 | False |
| 1 | 79 | 31 | 0.7182 | False |
| 2 | 79 | 31 | 0.7182 | False |
| 3 | 82 | 28 | 0.7455 | False |
| 4 | 80 | 30 | 0.7273 | False |
| 5 | 79 | 31 | 0.7182 | False |
| 6 | 81 | 29 | 0.7364 | False |

## Cost per answer

| iteration | decide wall (s) | answered | s/answer |
|---|---|---|---|
| 0 | 6705.920469 | 79 | 84.885069 |
| 1 | 5321.074208 | 79 | 67.35537 |
| 2 | 5270.0547 | 79 | 66.709553 |
| 3 | 4208.5107 | 80 | 52.606384 |
| 4 | 4194.290407 | 80 | 52.42863 |
| 5 | 23628.879784 | 79 | 299.099744 |
| 6 | 4580.403504 | 81 | 56.548191 |

## Way-census (last iteration)

- **AllInterval-019** — verdict: reachable (124.4372s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem02_label10** — verdict: unreachable (2.1121s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem03_label51** — verdict: unreachable (96.2012s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem04_label27** — verdict: reachable (23.0734s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem05_label42+token_ring.08.cil-2** — verdict: reachable (10.2529s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem05_label46+token_ring.12.cil-1** — verdict: reachable (10.2577s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem06_label40** — verdict: resource-out (1200.6739s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem06_label53** — verdict: resource-out (1200.7058s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem07_label01** — verdict: unreachable (513.5348s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem101_label01** — verdict: reachable (252.5248s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem10_label07** — verdict: unreachable (28.4943s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem10_label08** — verdict: unreachable (32.6156s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem11_label26** — verdict: resource-out (1200.6024s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem11_label40** — verdict: resource-out (1200.5868s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem11_label48** — verdict: resource-out (1200.5904s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem13_label23** — verdict: reachable (65.1423s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem16_label07** — verdict: unreachable (342.6115s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem17** — verdict: resource-out (274.685s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem17_label03** — verdict: resource-out (879.4516s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem18_label15** — verdict: resource-out (1201.0133s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem19_label00** — verdict: resource-out (1204.0777s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem19_label14** — verdict: resource-out (1203.3523s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem19_label36** — verdict: resource-out (1203.3441s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **adding.5.prop1-func-interl** — verdict: unreachable (0.2526s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **anderson.3.prop1-back-serstep** — verdict: reachable (0.1343s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **anderson.3.prop1-func-interl** — verdict: reachable (2.5678s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **at.6.prop1-back-serstep** — verdict: reachable (39.0404s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **benchmark04_conjunctive** — verdict: unreachable (0.8256s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **bin-suffix-5** — verdict: unreachable (0.2631s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **blocks.4.prop1-back-serstep** — verdict: resource-out (753.3416s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **brp.2.prop1-func-interl** — verdict: unreachable (0.8313s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **brp2.2.prop1-func-interl** — verdict: unreachable (0.5315s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **brp2.3.prop1-back-serstep** — verdict: unreachable (2.2344s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **brp2.3.prop2-func-interl** — verdict: unreachable (0.4723s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **brp2.6.prop3-back-serstep** — verdict: unreachable (3.1993s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **byte_add_1-1** — verdict: unreachable (2.5418s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **cambridge.7.prop2-back-serstep** — verdict: resource-out (1200.4066s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **cancel_var_through_overflow** — verdict: unreachable (1.1659s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **collision.6.prop1-func-interl** — verdict: unreachable (14.3979s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **deep-nested** — verdict: unreachable (1.8862s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **digits_bad_for** — verdict: unreachable (6.2524s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **dijkstra-u_valuebound1** — verdict: unreachable (55.3225s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **egcd-ll_unwindbound10** — verdict: resource-out (1200.367s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **egcd3-ll_unwindbound2** — verdict: reachable (8.3707s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **elevator.3.prop1-back-serstep** — verdict: unreachable (1.8505s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **elevator.4.prop1-func-interl** — verdict: unreachable (0.3953s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **elevator_spec1_product19.cil** — verdict: unreachable (56.8868s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **exit.5.prop1-func-interl** — verdict: unreachable (0.444s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **float8** — verdict: unreachable (4.2452s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **float_req_bl_1071** — verdict: unreachable (1.0589s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **float_req_bl_1092a** — verdict: unreachable (2.1838s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **freire1_valuebound1** — verdict: unreachable (24.1108s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **frogs.2.prop1-back-serstep** — verdict: reachable (12.272s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **frogs.5.prop1-func-interl** — verdict: unreachable (24.2666s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **gauss_sum.i.p+lhb-reducer** — verdict: unreachable (6.5108s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **gcd_2+newton_3_7** — verdict: reachable (151.5275s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **gcd_4+newton_3_3** — verdict: unreachable (429.24s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **hard-ll_valuebound20** — verdict: unreachable (32.3377s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **jm2006.c.i.v+cfa-reducer** — verdict: unreachable (0.6806s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **krebs.3.prop1-func-interl** — verdict: unreachable (0.4225s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **lamport_nonatomic.5.prop1-back-serstep** — verdict: resource-out (1200.3644s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **lamport_nonatomic.5.prop1-func-interl** — verdict: unreachable (70.8365s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **lann.4.prop1-back-serstep** — verdict: resource-out (1200.2901s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **lcm1_unwindbound2** — verdict: resource-out (1200.2971s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **lcm1_valuebound100** — verdict: resource-out (1200.3066s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **lcm2_unwindbound50** — verdict: resource-out (1200.28s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **leader_election.3.prop1-back-serstep** — verdict: resource-out (1200.343s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **loop3** — verdict: resource-out (1200.3871s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **mcs.3.prop1-back-serstep** — verdict: resource-out (1200.348s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **minepump_spec1_product14.cil** — verdict: unreachable (3.9975s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **minepump_spec2_product07.cil** — verdict: unreachable (4.2661s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **minepump_spec2_product54.cil** — verdict: unreachable (13.1251s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **minepump_spec3_product45.cil** — verdict: unreachable (8.4001s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **minepump_spec4_product16.cil** — verdict: unreachable (4.1999s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **mod3.c.v+sep-reducer** — verdict: unreachable (41.5896s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **mono-crafted_8** — verdict: unreachable (0.6812s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **msmie.3.prop1-func-interl** — verdict: unreachable (124.8876s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **newton_1_5** — verdict: reachable (17.191s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pals_lcr-var-start-time.5.1.ufo.UNBOUNDED.pals** — verdict: reachable (2.6628s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pals_lcr-var-start-time.6.1.ufo.UNBOUNDED.pals** — verdict: reachable (7.873s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pals_lcr.5.1.ufo.UNBOUNDED.pals+Problem12_label04** — verdict: resource-out (1204.5447s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pals_lcr.5.ufo.BOUNDED-10.pals+Problem12_label02** — verdict: resource-out (1201.6018s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pals_lcr.5_overflow.ufo.UNBOUNDED.pals+Problem12_label02** — verdict: resource-out (1201.5415s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pals_lcr.6.1.ufo.UNBOUNDED.pals+Problem12_label09** — verdict: resource-out (1201.5351s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pals_opt-floodmax.4.3.ufo.UNBOUNDED.pals** — verdict: reachable (2.1969s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pc_sfifo_1.cil-2+token_ring.05.cil-2** — verdict: reachable (2.2177s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pc_sfifo_2.cil-1+token_ring.11.cil-2** — verdict: resource-out (1200.4125s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pc_sfifo_2.cil-1+token_ring.13.cil-1** — verdict: reachable (7.6533s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pc_sfifo_3.cil+token_ring.04.cil-1** — verdict: unreachable (695.8011s, abc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pc_sfifo_3.cil+token_ring.08.cil-2** — verdict: reachable (4.8745s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **peg_solitaire.3.prop1-back-serstep** — verdict: resource-out (1200.2947s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pgm_protocol.2.prop5-back-serstep** — verdict: unreachable (6.9309s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pgm_protocol.3.prop5-func-interl** — verdict: unreachable (3.0823s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pgm_protocol.4.prop2-func-interl** — verdict: unreachable (2.8642s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pgm_protocol.7.prop1-back-serstep** — verdict: unreachable (6.1028s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pgm_protocol.7.prop2-back-serstep** — verdict: unreachable (12.4481s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **phases_2-1** — verdict: reachable (0.4229s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **psyco_io_1** — verdict: unreachable (3.5554s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **rether.4.prop1-back-serstep** — verdict: unreachable (4.3299s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **rushhour.4.prop1-func-interl** — verdict: unreachable (20.1897s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **s3_srvr_1b.cil** — verdict: unreachable (1.3938s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **simple_vardep_1** — verdict: unreachable (0.7405s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **sqrt_Newton_pseudoconstant** — verdict: resource-out (1200.6967s, residue); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **synapse.7.prop1-func-interl** — verdict: unreachable (55.7309s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **telephony.6.prop1-func-interl** — verdict: reachable (22.9737s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **token_ring.03.cil-2** — verdict: unreachable (701.755s, abc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **transmitter.10.cil** — verdict: reachable (5.4123s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **trex02-1** — verdict: unreachable (0.2755s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **up** — verdict: unreachable (1.0983s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **zonotope_2** — verdict: unreachable (13.4176s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]

## Terminal board

- `d4c59dafc402` [in-set] **native-procedure** — 29 distinct question(s), origins {'campaign': 29}

## Failure modes (the cost reading)

- `047c72860c26` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `07ae2830089a` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `09329fdb6058` — flat (14 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `0994f100a9e4` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `09f0596e0db3` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `0a32e821595b` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `0a792a80d5e2` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `0e494daca9f8` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `0eeb15fc3cbc` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `1076f81d405f` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `10c83d2b3a7d` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `120680e811c6` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `132461ea563a` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `13318ccee32c` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `1394af6fe4b3` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `15c010d32e2a` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `168db1ee9230` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `16bd614f72b7` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `1827c3936e76` — flat (8 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `18f344e7f22b` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `198bfc25080b` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `1a3ee8a52594` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `1b0d80fd8464` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `1b6b8dbe380a` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `1c37a1aacbc8` — exponential-in-k (18 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `1c6313c79000` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `1eeb0e504451` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `21dd897602c0` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `21f30584fd08` — flat (18 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `2310d7f97f1a` — flat (18 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `247061c3eb2d` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `2492434cea1e` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `25f6cb97c88a` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `26aaebe02bd4` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `27ee3e350e8c` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `27f4a73720b4` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `29ae9504a0ce` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `2ae97181964d` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `2be07c6fe991` — unmeasured (12 point(s)): no curve yet — probe more bounds before designing anything
- `2e3c935d8bda` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `32338fd4f8cf` — exponential-in-k (18 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `33586085ef53` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `33b91c6c52a2` — flat (14 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `3419db378385` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `34246a39b97c` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `34d62ac11131` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `359abff111dc` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `35a6d2d17fdd` — exponential-in-k (18 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `3a4cc07f937e` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `3ae666b0bead` — exponential-in-k (15 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `3bf8f859394d` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `3cbe3d52d067` — flat (14 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `3cf4afe90730` — exponential-in-k (18 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `3de26e4c339c` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `42ee8d6085f2` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `436e525fb65c` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `44c6298003b9` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `455b311c1b2a` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `46ade92bbce7` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `496297821e1e` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `4a21117c2dc1` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `4a3020ad7c49` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `4a98dd986bfb` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `4acf18c63d3f` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `4b5c1fdaf31d` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `4b7f0d1e8642` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `4ca94e6cbae8` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `4f2a73d14328` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `50ec0bd2ed7a` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `51b5162c5f82` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `51cbec8b6725` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `53e92a21be0b` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `565643f6f244` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `5985786543d1` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `59db389bc375` — flat (8 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `5a51f68811a7` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `5a73a66a3f45` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `5ad6d87fea0e` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `5c276677289e` — flat (8 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `5e67ea610075` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `5f5fb33120c2` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `611f8fb590b2` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `6127d353bd87` — flat (12 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `631a4bc218f8` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `63290e005198` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `634ed4aff6ed` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `643cea6460af` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `65402994dee4` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `65b57b174ff9` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `668e6531597b` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `66aad9f76827` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `6827fd4d3fc2` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `68331a9d009a` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `6b01d48b8012` — unmeasured (12 point(s)): no curve yet — probe more bounds before designing anything
- `6b3dc94f590e` — flat (15 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `6d12958889a7` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `6d42a617f26f` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `6db2488767df` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `6e07a14afe1c` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `6e9980182009` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `70e69a2971f2` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `713f0e93d1c2` — flat (18 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `716dd61c9f24` — exponential-in-k (18 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `7268471b6542` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `72860141439d` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `755dd5271d27` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `75843d8f6160` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `76616f320cbf` — unmeasured (12 point(s)): no curve yet — probe more bounds before designing anything
- `77c9b4631f4c` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `79f5c1fea10f` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `7a0fea741ef8` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `7a8ddf619fff` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `7cae582acd5c` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `7d51357b414a` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `7e5116d2f92b` — unmeasured (6 point(s)): no curve yet — probe more bounds before designing anything
- `7e82df04cd00` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `7e8e902882ce` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `7efd8f941716` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `801755a50119` — flat (18 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `81363cd74f1f` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `8200ed54f300` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `8245fa26f8e4` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `839afb88e853` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `846f047e0536` — flat (18 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `85cfc833633d` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `867bb4b02fa1` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `86f3325e42a3` — flat (12 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `8775da989564` — unmeasured (6 point(s)): no curve yet — probe more bounds before designing anything
- `88c218993769` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `893d78af216b` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `8f03434f1e01` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `90476c9ce281` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `90d751dd03cd` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `91cda7c2f4f0` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `922f9ff9eac5` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `926a4c642dd5` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `927372e149da` — unmeasured (6 point(s)): no curve yet — probe more bounds before designing anything
- `975af8edd7af` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `978a4db1ac50` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `99755693ebe2` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `9c7fbfa5e21b` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `9d24496172ff` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `a0192d6e1929` — flat (8 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `a01cd64499f2` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `a6fef26e0316` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `a9ed476c6cfe` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `aa79819d9f95` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `ab4af5b27e33` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `adc6de37346f` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `aee9b5aee5c4` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `af5441359805` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `afec8c0cdb49` — flat (18 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `b0881a33b9ea` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `b5fca65f3a7b` — exponential-in-k (18 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `b6cec4c43607` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `b70150560b51` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `b8240e5009c3` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `b8f1bda834cd` — flat (8 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `b92a38797ed1` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `b98a421c2699` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `b9c48057033d` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `ba188b9cf98b` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `bac80abbabd2` — flat (8 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `bb1548be035e` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `bbea6eda6e80` — flat (12 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `bc1b010f0eac` — flat (18 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `be00d3933a85` — flat (18 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `be0ba86462b3` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `be8c68b85736` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `c064ba114ce5` — unmeasured (13 point(s)): no curve yet — probe more bounds before designing anything
- `c084a0dc6f82` — flat (17 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `c1fb4fd0871f` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `c24bf71e8b37` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `c2c8a0a86b45` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `c651d293c62d` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `c7ffe2365423` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `c9120928e00e` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `cbcf3febbd8f` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `cd7e0ad924bb` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `cdb52c840b94` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `cdd95fecdea9` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `d06aae4f2b6d` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `d0bfac56bfb8` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `d0e890896e25` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `d171ccfa40fa` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `d27b7b27a024` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `d32b612c9fed` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `d5600ef34f79` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `d80ace180476` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `d83418d9b5aa` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `d95b421396b4` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `da056b7597de` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `da753448a4a3` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `dbee5752ffe2` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `dc30fd95baea` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `dd04e951d38f` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `de1a1e9c9b2a` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `de27cb565bd0` — unmeasured (6 point(s)): no curve yet — probe more bounds before designing anything
- `e0dfdf2b6319` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `e0f9ff7df0d3` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `e295bb4ae732` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `e4c403715215` — unmeasured (12 point(s)): no curve yet — probe more bounds before designing anything
- `e4f70ef18933` — flat (15 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `e70329df0189` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `e8d1397abab8` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `e8ec7a848035` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `e9ab5408d95e` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `eb42e57940a1` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `ed7ec28eb028` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `edc201c66562` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `edc4553c2d68` — exponential-in-k (18 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `ee5a36e17fcd` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `f0640feb798f` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `f1c4fe5b5e36` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `f31ecfe34f50` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `f4674a8eea90` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `f4797cc21a75` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `f5154c143816` — flat (18 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `f5c3b5cc4f1c` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `f6fdd4d24514` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `fa7591de8bb3` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `fa9599ab472f` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `faa70213063c` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `fd28c90578a9` — unmeasured (14 point(s)): no curve yet — probe more bounds before designing anything
- `fd8794f08833` — unmeasured (7 point(s)): no curve yet — probe more bounds before designing anything
- `fdb68523df52` — flat (8 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth
- `fed73b3e9be1` — flat (10 point(s)): cost is not k-bound at these scales — if blocked, look at instance size or engine choice, not depth

---

Generated by `tools/saturation_report.py` from `iterations.jsonl` — regenerating from the same input is byte-identical; `unknown`/`resource-out` are counted, never hidden.

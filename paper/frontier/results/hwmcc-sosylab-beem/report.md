# Saturation report — `hwmcc-sosylab-beem`

Source: `github:CyanoKobalamyne/hwmcc-benchmarks@57174f5d6f575aedcfe83694b35ec8e7b83043fc` (110 questions, sha256-pinned). Caps: `{"decide_wall_s": 300, "engine": "native", "k": 20, "probe_ks": [2, 4, 8]}` — capped results are capped, never full-suite.

**Saturated: False**

## The curve

| iteration | solved | open | answered | saturated |
|---|---|---|---|---|
| 0 | 79 | 31 | 0.7182 | False |

## Cost per answer

| iteration | decide wall (s) | answered | s/answer |
|---|---|---|---|
| 0 | 6705.920469 | 79 | 84.885069 |

## Way-census (last iteration)

- **AllInterval-019** — verdict: reachable (268.3177s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem02_label10** — verdict: unreachable (2.8748s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem03_label51** — verdict: unreachable (131.2885s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem04_label27** — verdict: reachable (28.2354s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem05_label42+token_ring.08.cil-2** — verdict: reachable (11.3813s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem05_label46+token_ring.12.cil-1** — verdict: reachable (11.3237s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem06_label40** — verdict: resource-out (300.0324s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem06_label53** — verdict: resource-out (300.0254s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem07_label01** — verdict: unreachable (533.9305s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem101_label01** — verdict: reachable (248.3596s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem10_label07** — verdict: unreachable (29.6674s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem10_label08** — verdict: unreachable (32.7563s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem11_label26** — verdict: resource-out (300.0584s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem11_label40** — verdict: resource-out (300.0574s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem11_label48** — verdict: resource-out (300.0618s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem13_label23** — verdict: reachable (74.9493s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem16_label07** — verdict: unreachable (362.8538s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem17** — verdict: resource-out (301.6962s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem17_label03** — verdict: resource-out (300.1743s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem18_label15** — verdict: resource-out (300.0824s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem19_label00** — verdict: resource-out (300.1993s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem19_label14** — verdict: resource-out (300.4213s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **Problem19_label36** — verdict: resource-out (300.2976s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **adding.5.prop1-func-interl** — verdict: unreachable (0.2303s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **anderson.3.prop1-back-serstep** — verdict: reachable (0.1029s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **anderson.3.prop1-func-interl** — verdict: reachable (2.6651s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **at.6.prop1-back-serstep** — verdict: reachable (40.7973s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **benchmark04_conjunctive** — verdict: unreachable (0.9974s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **bin-suffix-5** — verdict: unreachable (0.2587s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **blocks.4.prop1-back-serstep** — verdict: resource-out (300.0079s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **brp.2.prop1-func-interl** — verdict: unreachable (0.7985s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **brp2.2.prop1-func-interl** — verdict: unreachable (0.4941s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **brp2.3.prop1-back-serstep** — verdict: unreachable (2.265s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **brp2.3.prop2-func-interl** — verdict: unreachable (0.4448s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **brp2.6.prop3-back-serstep** — verdict: unreachable (3.1401s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **byte_add_1-1** — verdict: unreachable (2.5871s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **cambridge.7.prop2-back-serstep** — verdict: resource-out (300.0084s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **cancel_var_through_overflow** — verdict: unreachable (2.2425s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **collision.6.prop1-func-interl** — verdict: unreachable (14.8809s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **deep-nested** — verdict: unreachable (2.3081s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **digits_bad_for** — verdict: unreachable (5.9014s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **dijkstra-u_valuebound1** — verdict: unreachable (72.9371s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **egcd-ll_unwindbound10** — verdict: resource-out (300.0222s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **egcd3-ll_unwindbound2** — verdict: reachable (17.1559s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **elevator.3.prop1-back-serstep** — verdict: unreachable (1.8315s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **elevator.4.prop1-func-interl** — verdict: unreachable (0.3559s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **elevator_spec1_product19.cil** — verdict: unreachable (117.882s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **exit.5.prop1-func-interl** — verdict: unreachable (0.4048s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **float8** — verdict: unreachable (4.1777s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **float_req_bl_1071** — verdict: unreachable (1.1657s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **float_req_bl_1092a** — verdict: unreachable (2.2498s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **freire1_valuebound1** — verdict: unreachable (49.3485s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **frogs.2.prop1-back-serstep** — verdict: reachable (12.3501s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **frogs.5.prop1-func-interl** — verdict: unreachable (23.2621s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **gauss_sum.i.p+lhb-reducer** — verdict: unreachable (8.2241s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **gcd_2+newton_3_7** — verdict: reachable (161.8617s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **gcd_4+newton_3_3** — verdict: unreachable (445.5646s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **hard-ll_valuebound20** — verdict: unreachable (76.2557s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **jm2006.c.i.v+cfa-reducer** — verdict: unreachable (0.7889s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **krebs.3.prop1-func-interl** — verdict: unreachable (0.3798s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **lamport_nonatomic.5.prop1-back-serstep** — verdict: resource-out (300.006s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **lamport_nonatomic.5.prop1-func-interl** — verdict: unreachable (71.0023s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **lann.4.prop1-back-serstep** — verdict: resource-out (300.0067s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **lcm1_unwindbound2** — verdict: resource-out (300.0103s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **lcm1_valuebound100** — verdict: resource-out (300.0119s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **lcm2_unwindbound50** — verdict: resource-out (300.0077s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **leader_election.3.prop1-back-serstep** — verdict: resource-out (300.0103s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **loop3** — verdict: resource-out (300.0203s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **mcs.3.prop1-back-serstep** — verdict: resource-out (300.0065s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **minepump_spec1_product14.cil** — verdict: unreachable (8.6019s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **minepump_spec2_product07.cil** — verdict: unreachable (8.179s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **minepump_spec2_product54.cil** — verdict: unreachable (25.4787s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **minepump_spec3_product45.cil** — verdict: unreachable (16.3959s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **minepump_spec4_product16.cil** — verdict: unreachable (8.3486s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **mod3.c.v+sep-reducer** — verdict: unreachable (47.5123s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **mono-crafted_8** — verdict: unreachable (0.8006s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **msmie.3.prop1-func-interl** — verdict: unreachable (110.1297s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **newton_1_5** — verdict: reachable (16.8336s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pals_lcr-var-start-time.5.1.ufo.UNBOUNDED.pals** — verdict: reachable (4.9921s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pals_lcr-var-start-time.6.1.ufo.UNBOUNDED.pals** — verdict: reachable (14.8776s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pals_lcr.5.1.ufo.UNBOUNDED.pals+Problem12_label04** — verdict: resource-out (300.1176s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pals_lcr.5.ufo.BOUNDED-10.pals+Problem12_label02** — verdict: resource-out (300.0817s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pals_lcr.5_overflow.ufo.UNBOUNDED.pals+Problem12_label02** — verdict: resource-out (300.0847s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pals_lcr.6.1.ufo.UNBOUNDED.pals+Problem12_label09** — verdict: resource-out (300.2335s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pals_opt-floodmax.4.3.ufo.UNBOUNDED.pals** — verdict: reachable (5.1158s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pc_sfifo_1.cil-2+token_ring.05.cil-2** — verdict: reachable (2.5957s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pc_sfifo_2.cil-1+token_ring.11.cil-2** — verdict: resource-out (300.0174s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pc_sfifo_2.cil-1+token_ring.13.cil-1** — verdict: reachable (9.8711s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pc_sfifo_3.cil+token_ring.04.cil-1** — verdict: resource-out (300.0108s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pc_sfifo_3.cil+token_ring.08.cil-2** — verdict: reachable (4.6226s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **peg_solitaire.3.prop1-back-serstep** — verdict: resource-out (300.0086s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pgm_protocol.2.prop5-back-serstep** — verdict: unreachable (6.904s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pgm_protocol.3.prop5-func-interl** — verdict: unreachable (3.0476s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pgm_protocol.4.prop2-func-interl** — verdict: unreachable (2.811s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pgm_protocol.7.prop1-back-serstep** — verdict: unreachable (6.06s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **pgm_protocol.7.prop2-back-serstep** — verdict: unreachable (12.3291s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **phases_2-1** — verdict: reachable (0.3792s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **psyco_io_1** — verdict: unreachable (7.0569s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **rether.4.prop1-back-serstep** — verdict: unreachable (4.4779s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **rushhour.4.prop1-func-interl** — verdict: unreachable (20.0757s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **s3_srvr_1b.cil** — verdict: unreachable (2.7282s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **simple_vardep_1** — verdict: unreachable (0.6816s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **sqrt_Newton_pseudoconstant** — verdict: resource-out (300.1287s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **synapse.7.prop1-func-interl** — verdict: unreachable (54.8559s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **telephony.6.prop1-func-interl** — verdict: reachable (23.2739s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **token_ring.03.cil-2** — verdict: resource-out (300.0131s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **transmitter.10.cil** — verdict: reachable (10.5906s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **trex02-1** — verdict: unreachable (0.2873s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **up** — verdict: unreachable (1.3002s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]
- **zonotope_2** — verdict: unreachable (15.39s, btormc); ways: btor2-smtlib [universal/exact], (native) [universal/exact]

## Terminal board

- `9c26710bf77f` [in-set] **reduction** — 31 distinct question(s), origins {'campaign': 31}, registered in flight: btor2-havoc

## Failure modes (the cost reading)

- `09329fdb6058` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `0994f100a9e4` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `0a32e821595b` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `10c83d2b3a7d` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `120680e811c6` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `132461ea563a` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `15c010d32e2a` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `16bd614f72b7` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `1b0d80fd8464` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `1c37a1aacbc8` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `1c6313c79000` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `1eeb0e504451` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `21f30584fd08` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `2310d7f97f1a` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `247061c3eb2d` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `2492434cea1e` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `26aaebe02bd4` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `27ee3e350e8c` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `27f4a73720b4` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `29ae9504a0ce` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `2ae97181964d` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `2be07c6fe991` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `2e3c935d8bda` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `32338fd4f8cf` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `33b91c6c52a2` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `3419db378385` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `34246a39b97c` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `35a6d2d17fdd` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `3a4cc07f937e` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `3ae666b0bead` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `3cbe3d52d067` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `3cf4afe90730` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `3de26e4c339c` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `44c6298003b9` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `46ade92bbce7` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `4a3020ad7c49` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `4b5c1fdaf31d` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `4b7f0d1e8642` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `51b5162c5f82` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `565643f6f244` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `5985786543d1` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `634ed4aff6ed` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `643cea6460af` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `65402994dee4` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `65b57b174ff9` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `668e6531597b` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `6b01d48b8012` — unmeasured (4 point(s)): no curve yet — probe more bounds before designing anything
- `6b3dc94f590e` — linear-in-k (6 point(s)): depth is affordable — raise k within budget before demanding a new instrument
- `6d12958889a7` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `6db2488767df` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `70e69a2971f2` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `713f0e93d1c2` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `716dd61c9f24` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `72860141439d` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `76616f320cbf` — unmeasured (4 point(s)): no curve yet — probe more bounds before designing anything
- `77c9b4631f4c` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `7a0fea741ef8` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `7a8ddf619fff` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `7cae582acd5c` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `7d51357b414a` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `7e5116d2f92b` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `7e8e902882ce` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `7efd8f941716` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `801755a50119` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `8200ed54f300` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `846f047e0536` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `8775da989564` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `8f03434f1e01` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `91cda7c2f4f0` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `926a4c642dd5` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `927372e149da` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `975af8edd7af` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `aa79819d9f95` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `ab4af5b27e33` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `adc6de37346f` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `af5441359805` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `afec8c0cdb49` — linear-in-k (6 point(s)): depth is affordable — raise k within budget before demanding a new instrument
- `b5fca65f3a7b` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `bbea6eda6e80` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `bc1b010f0eac` — linear-in-k (6 point(s)): depth is affordable — raise k within budget before demanding a new instrument
- `be00d3933a85` — linear-in-k (6 point(s)): depth is affordable — raise k within budget before demanding a new instrument
- `c064ba114ce5` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `c084a0dc6f82` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `c24bf71e8b37` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `c7ffe2365423` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `cbcf3febbd8f` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `cd7e0ad924bb` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `cdb52c840b94` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `d0bfac56bfb8` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `d5600ef34f79` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `d83418d9b5aa` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `d95b421396b4` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `da056b7597de` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `da753448a4a3` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `dc30fd95baea` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `de1a1e9c9b2a` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `de27cb565bd0` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `e0dfdf2b6319` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `e295bb4ae732` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `e4c403715215` — unmeasured (4 point(s)): no curve yet — probe more bounds before designing anything
- `e4f70ef18933` — linear-in-k (6 point(s)): depth is affordable — raise k within budget before demanding a new instrument
- `e8ec7a848035` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `edc4553c2d68` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `ee5a36e17fcd` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `f4797cc21a75` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `f5154c143816` — exponential-in-k (6 point(s)): deeper BMC will not close this: an unbounded engine (k-induction / interpolation) or a property transformation — or an abstraction pair if the cone is small
- `fa7591de8bb3` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything
- `fa9599ab472f` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `fd28c90578a9` — unmeasured (2 point(s)): no curve yet — probe more bounds before designing anything
- `fd8794f08833` — unmeasured (1 point(s)): no curve yet — probe more bounds before designing anything

---

Generated by `tools/saturation_report.py` from `iterations.jsonl` — regenerating from the same input is byte-identical; `unknown`/`resource-out` are counted, never hidden.

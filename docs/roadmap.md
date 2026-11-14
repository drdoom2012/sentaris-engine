# Sentaris Engine — Implementation Roadmap

**Status:** Approved (2026-11-11); amended 2026-11-12 (SE-5b), 2026-11-13 (OD-27), 2026-11-13 (OD-13, section 6.9) and 2026-11-14 (OD-6, OD-7, OD-23, section 6.10; OD-4, section 6.8; OD-24, section 6.11). Nothing is built.  
**Source:** `docs/domain.md`. This roadmap cites rules and decisions by ID (`DR-xx`, `OD-xx`) and does not restate them. If the two disagree, the domain document wins.

The roadmap splits the path from an empty repository to live scanning and historical replay into slices (`SE-n`). Each slice goes through the usual cycle: plan, independent review, implementation, independent review.

## 1. How to read it

- **Phase A (SE-1 to SE-6)** needs no open decision and can start now.
- Every later slice is behind a **decision gate**: the open decisions (domain section 7) that the user must take before the slice is planned. No slice settles an open decision by implementation.
- Each slice table has a **Depends on** column (slices that must be finished) and a **Gate** column (decisions that must be taken). Section 4 shows the same dependencies and gates as a diagram.
- A slice is finished when `make check` passes and every rule it claims to enforce has a named negative test (domain section 8).
- Slice numbers give a recommended order, not a strict one.

## 2. Slices

### Phase A — Core, buildable now

| Slice | Content | Domain reference | Depends on | Gate |
|---|---|---|---|---|
| **SE-1** Project skeleton | Python package, test runner, linter, type checker, `make check`. Automated architecture checks: domain and strategy code import no I/O, clock or randomness; no Quasar code is imported; no trading or exchange dependency. | DR-08, DR-18, DR-19 | none | none |
| **SE-2** Payload values and canonical form | Accepted and rejected values, freezing by copy, duplicate-key rejection, canonical encoder, strict decoder, equality by canonical form. All test vectors of Appendix A.3. | Section 6.3, Appendix A, DR-10, DR-11, DR-13 | SE-1 | none |
| **SE-3** Evaluation types | Time (instants and durations), parameters, signal, the three-outcome result, the snapshot container with the row types of the three inputs, evaluation context. Types only, no behavior beyond validation. The instrument key is handled only as the opaque non-empty string of section 6.8, so these types do not depend on its format. Checking a key against actual Quasar data belongs to SE-7b and OD-4. | Sections 5, 6.1, 6.2, 6.5, 6.6, 6.8; DR-14 | SE-2 | none |
| **SE-4** Strategy contract and stateless evaluation | Strategy identity; the stateless contract and the evaluation of one stateless strategy as a pure transition, fully implemented; the stateful contract **as a type only**. Loading state, running a stateful transition and continuity belong to SE-14. Test strategies only; no real strategy. Determinism test: repeated evaluation gives identical output. | Section 6.4, DR-12, DR-22, DR-23, DR-26 | SE-3 | none |
| **SE-5** Execution over pairs | One `as_of`, explicit pairs, one prebuilt snapshot per instrument, ordering, refused input, isolation of a strategy that raises, the report. Stateless pairs only; stateful pairs wait for SE-14. Malformed parameters (domain section 6.5) are SE-5b's. | Section 6.7, DR-10, DR-22 | SE-4 | none |
| **SE-6** Quasar REST client | Transport only: reading candles, open interest and funding through the REST API, paging, exact decimal parsing, error mapping. It takes Quasar's own series identifiers and makes no statement about availability, completeness or consistency. Tested against fixtures written from the Quasar contract. | Section 5, DR-11, DR-18 | SE-3 | none |

SE-6 is independent of SE-4 and SE-5 and may run in parallel with them.

### Phase B — Snapshot building

| Slice | Content | Domain reference | Depends on | Gate |
|---|---|---|---|---|
| **SE-7a** Input declaration | How a strategy declares the inputs it needs, and how the needs of the pairs of one instrument are combined into what is read for that instrument (domain section 6.9). Narrowing each pair's snapshot to its own declaration needs the lookback boundaries and belongs to SE-7b. Pure domain code, no I/O. | Sections 6.4, 6.7, 6.9 | SE-4 | none (OD-13 part decided 2026-11-13, section 6.9) |
| **SE-7b** Snapshot builder: candles | Instrument key to Quasar series, including checking the key against actual Quasar data; reading through the client; reading each instrument's data once and building each pair's immutable snapshot narrowed to its own declaration (domain section 6.9); candle availability. DR-07 test for candles. | DR-01, DR-02, DR-05, DR-06, DR-07, DR-20 | SE-6, SE-7a | OD-13 (remainder: which rows a lookback holds at its boundaries) |
| **SE-8** Snapshot builder: open interest | Open interest availability and its relation to candles through the contract's instants. DR-07 test. | DR-03, DR-07, DR-20, DR-24 | SE-7b | none beyond SE-7b's |
| **SE-9** Snapshot builder: funding | Funding selection and availability. DR-07 test. | DR-03, DR-04, DR-07, DR-24 | SE-7b | OD-16 |

SE-7 is split because the two parts have different gates and different test setups. SE-7a is pure and needs only OD-13, so it could be built while the availability decisions (OD-6, OD-7) were still open. SE-7b needs the client, fixtures of Quasar data and the availability decisions. Availability rests on an ingestion time that Quasar's contract does not expose yet (domain section 6.10); until it does, SE-7b's snapshot builder fails closed over real Quasar data, and its tests use fixtures that carry the field.

SE-8 and SE-9 are needed only once a strategy uses those inputs.

### Phase C — Data quality and the first strategy

| Slice | Content | Domain reference | Depends on | Gate |
|---|---|---|---|---|
| **SE-5b** Malformed parameters in execution | A pair whose parameters are refused gets an evaluation failure for that pair alone, without calling the strategy; the other pairs are unaffected. | Sections 6.5, 6.7; DR-14, DR-22 | SE-5 | OD-3 (the code for malformed parameters) |
| **SE-10** Data-quality gate | Validation before evaluation, the failure-code taxonomy, who produces a failure, what the pairs of an instrument report when its snapshot cannot be built. | DR-14 to DR-17, section 6.7 | SE-5, SE-7b | OD-3 (remainder), OD-8 |
| **SE-11** Indicators | Only if a strategy needs indicators: the decided source and numeric policy. | DR-11, DR-15 | SE-3; SE-6 if Quasar's indicators are the decided source | OD-9 |
| **SE-12** First real strategy | One stateless strategy, specified on its own request, evaluated end to end over fixture data. Every strategy specification states whether the strategy depends on earlier evaluations (phases, a path over time, signals already emitted) and, if it does, why that cannot be recomputed from a bounded window of data (OD-27); a strategy that needs state goes to OD-27 before it is planned. | Domain section 3 ("Out of scope"), DR-12 | SE-10, SE-5b; SE-8, SE-9 and SE-11 only if the strategy uses them | The strategy's own specification; OD-13 (where specifications live) |

### Phase D — Live scanning

| Slice | Content | Domain reference | Depends on | Gate |
|---|---|---|---|---|
| **SE-13** Live scanning | Composition root: configured pairs, choice of the live `as_of`, repeated execution, what happens to results as decided in OD-11. Stateless strategies only. | Sections 3 ("Live"), 6.7; DR-08 | SE-12 | OD-5 (live part), OD-11; OD-18 and OD-25 if results are persisted or delivered |

**Stateful live execution** is not part of SE-13. It requires SE-14 as well, and SE-15 with its gate if the decisions on persistence and commit (OD-11, OD-18, OD-20) require state to be recorded.

Per the "Consequence for trust" in domain section 5, SE-13 is the first point at which a signal over real Quasar data may exist, and only once Quasar serves the ingestion time (domain section 6.10).

### Phase E — Strategy state

| Slice | Content | Domain reference | Depends on | Gate |
|---|---|---|---|---|
| **SE-14** State handling in execution | Evaluation scope, loading and passing `previous_state`, running the stateful transition, receiving `next_state`, state after a failure or a raise, continuity. State stays opaque. Tested with test strategies. | DR-25, DR-26, DR-27, section 6.7 | SE-5 | OD-27, OD-17, OD-19, OD-20 |
| **SE-15** State persistence and commit | Only if persistence is wanted (domain section 2, "Open"): the state store, encoding, consistent commit of state and signals. | DR-28, DR-13 | SE-14 | OD-11, OD-18, OD-20; OD-25 if signals are persisted or delivered |

### Phase F — Historical replay

| Slice | Content | Domain reference | Depends on | Gate |
|---|---|---|---|---|
| **SE-16** Replay runner | The generic runner: execution over a range of past `as_of` values on one consistent dataset, through the same pipeline as live (snapshot builder, data-quality gate, execution). Stateless strategies only. Tested with test strategies over fixtures of Quasar data; repeated-run identity test. | DR-12, DR-13, DR-21, section 3 ("Historical replay") | SE-10 | OD-5 (replay step and range), OD-12; OD-24 (remainder) only if a kept dataset is requested |

SE-16 does not depend on SE-12: test strategies are enough to build and test the runner.

**Replaying a real strategy** needs no slice of its own. It requires SE-16 and SE-12, plus the input slices that strategy uses.

**Stateful replay** requires SE-14 as well, and the decision in OD-17 on how a replay's state is kept apart from live state (DR-27).

**Trust requirements are unchanged.** SE-16 reads history only through the snapshot builder, so sections 6.10 and 6.11 apply to it in full. A replay output may be described as reproducing what a live evaluation would have produced only with the accepted differences and the clock assumption of domain section 6.10 (domain section 5, "Consequence for trust").

### Not on the path

These are added only on explicit request (domain section 2): cross-instrument context (OD-22), a REST endpoint and notifications (OD-11), evaluation of replay output as a backtest (OD-12).

## 3. Recommended order of decisions

Decisions are listed in the order they start to block work. Phase A gives time to take the first groups.

| Order | Decisions | Unblocks | Note |
|---|---|---|---|
| 1 | OD-6, OD-7, OD-23 (decided) | SE-7b | OD-6, OD-7 and OD-23 were decided on 2026-11-14 (domain section 6.10) and are closed. Quasar's contract defines the ingestion time per row (its section 4.1); until it is deployed, evaluations over real data fail closed. |
| 2 | OD-13 (remainder) | SE-7a, SE-7b | The declaration and shared reading were decided 2026-11-13 (domain section 6.9), which unblocks SE-7a. The lookback boundaries remain for SE-7b; where strategy specifications live remains for the first real strategy. |
| 3 | OD-4, OD-24 (decided) | SE-7b, SE-16 | OD-4 was decided on 2026-11-14 (domain section 6.8) and is closed. OD-24 was decided on 2026-11-14 (domain section 6.11) except whether a replay's dataset is kept, which matters only if that is requested. |
| 4 | OD-3 (remainder), OD-8 | SE-10, SE-5b | |
| 5 | First strategy specification; OD-9 and OD-16 if it uses indicators or funding | SE-12, SE-11, SE-9 | The strategy's needs show which inputs and indicators matter. |
| 6 | OD-5, OD-11; OD-18 and OD-25 if results leave memory | SE-13, SE-16 (OD-5) | |
| 7 | OD-27, then OD-17, OD-19, OD-20 | SE-14, SE-15 | Only when a stateful strategy is requested. OD-27 first: it decides whether these are needed at all. |
| 8 | OD-12 | SE-16 | |

## 4. Dependencies

Square brackets are the gate a slice waits for, in addition to the slices before it.

```text
SE-1 → SE-2 → SE-3 ─┬→ SE-4 ─┬→ SE-5 ─┬─────────────────────────────────────────────────────┐
                    │        │        └→ [OD-27, OD-17, OD-19, OD-20] SE-14                 │
                    │        │              └→ [OD-11, OD-18, OD-20] SE-15                  │
                    │        └→ SE-7a ─────────┐                                            │
                    ├→ SE-6 ───────────────────┴→ [OD-13] SE-7b ──────────────────────────┬─┴→ [OD-3, OD-8] SE-10
                    │                                                                     ├→ SE-8
                    │                                                                     └→ [OD-16] SE-9
                    └→ [OD-9] SE-11

SE-10 ─┬→ [strategy specification, OD-13] SE-12 → [OD-5, OD-11] SE-13
       └→ [OD-5, OD-12] SE-16

SE-5 → [OD-3] SE-5b → SE-12

Optional inputs of SE-12, only if the strategy uses them: SE-8, SE-9, SE-11.
```

Combinations that are not slices:

| Capability | Requires |
|---|---|
| Replay of a real strategy | SE-16, SE-12 |
| Stateful live execution | SE-13, SE-14; SE-15 if state must be recorded |
| Stateful replay | SE-16, SE-14, OD-17 (replay state kept apart from live) |

After SE-10, live scanning (SE-12, SE-13) and replay (SE-16) are independent of each other. State (SE-14, SE-15) depends only on SE-5 and its gate.

## 5. Choices made in this roadmap

These were chosen while drafting and are open to correction:

- Slice numbering starts again at SE-1.
- SE-4 implements the stateful contract as a type only, and SE-5 handles stateless pairs only. All state behavior is in SE-14, because every aspect of it is open (OD-17 to OD-20).
- The Quasar client (SE-6) is placed in Phase A as pure transport, so that no gate blocks it.
- SE-7 is split into SE-7a and SE-7b; the other numbers are kept.
- The snapshot builder is split by input (SE-7b, SE-8, SE-9), so that funding (OD-16) does not block candles.
- SE-16 is the generic replay runner and is tested with test strategies.
- Tooling (package manager, linter, type checker) is chosen in the SE-1 plan.

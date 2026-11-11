# ADR-0002: Multi-strategy execution

- **Status:** Accepted (approved by the user on 2026-11-11, each item as proposed in the SE-2 session; the failure report in the form "a separate result type").
- **Date:** 2026-11-11
- **Scope:** how one execution runs several strategies for one `as_of`: snapshot sharing, order, concurrency, and how one strategy's failure is reported next to the others' results.
- **Spec:** `docs/superpowers/specs/2026-11-09-engine-roadmap-design.md` (slice SE-2)
- **Decides:** OD-15 (`docs/domain.md`, section 10)

## Context

Slice SE-2 evaluates several strategies for one `as_of` and collects one report per strategy. `docs/domain.md` left four points open in OD-15, and section 10 forbids deciding them by implementation. DR-10 (no dependence on iteration order) and DR-22 (a strategy's result depends only on its own evaluation context; another strategy's failure changes nothing) bound the answer.

## Decisions

| Point | Decision | Reason |
|---|---|---|
| Snapshot | Strategies share the one immutable snapshot of an `as_of`. Each strategy is evaluated on its own evaluation context (its own parameters over that snapshot). Execution never changes or copies a snapshot. | A snapshot is an immutable value, so sharing it cannot let one strategy affect another (DR-22), and one snapshot per `as_of` is what DR-05 asks for. |
| Order | Strategies run in ascending order of `(id, version)`, compared as strings by Unicode code point. The report lists them in that order. The order of registration changes neither the results nor their order. Two strategies with the same `(id, version)` are refused. | DR-10 requires explicit sorting. Identity is `id` and `version` (OD-13), so it is the key every strategy already has. |
| Concurrency | None. Strategies run one after another in one thread. | No measured need (roadmap section 2). Adding it later must not change results, which the order rule already requires. |
| Failure | An exception raised by a strategy is caught for that strategy alone and reported as its own report entry. The entry is a **separate result type**, distinct from the three outcomes of DR-14, and carries the strategy's `id`, `version` and the exception's type name, never its message. A strategy whose result breaks the contract (`StrategyContractError` from the result check, SE-1) is reported the same way. A strategy whose `id` or `version` is not a valid identity cannot be ordered, checked for duplicates or named in a report entry, so it is refused for the whole execution (`StrategyContractError`) before any strategy runs, exactly as a duplicate `(id, version)` is. Identity is read once per execution. Only `Exception` is caught; `BaseException` that is not an `Exception` (such as `KeyboardInterrupt`) propagates. | `EvaluationFailure` is what a strategy returns when it cannot decide (DR-14); an exception is an engine-level event, and the taxonomy of failure codes is still open (OD-3, expected with SE-6), so the two are not mixed. An exception message may carry data of the strategy's context, so it is not copied into a report. |

## Consequences

- A report entry exists for every strategy, including the failed one (DR-14, DR-22); a failure never disappears into an empty result.
- A strategy's report entry is the same whether it runs alone or with others (DR-22). SE-2's tests show it with a raising probe beside a healthy one.
- **Limit of "shared snapshot".** SE-2 takes each evaluation context as given by the caller. Whether one snapshot then holds the union of the inputs that the strategies need, or one snapshot is built per input set, depends on how a strategy declares its inputs (rest of OD-13, expected with SE-5) and is not decided here.
- **State is not part of SE-2.** For a strategy with state the same rules apply to order and failure; loading and persisting state, and what a failure leaves behind, stay with OD-17 to OD-20 and SE-3.
- The name and fields of the failure entry and of the report are left to the SE-2 plan. This ADR fixes only what the entry must carry and must not carry.
- Still open and not touched: the failure-code taxonomy (OD-3), `as_of` selection (OD-5).

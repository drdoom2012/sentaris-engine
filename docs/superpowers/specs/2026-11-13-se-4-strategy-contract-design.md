# SE-4 — Strategy contract and stateless evaluation: design

**Slice:** SE-4 (`docs/roadmap.md`, Phase A)  
**Status:** Revision 4, approved by the user together with section 13 (2026-11-13). Amended 2026-11-13 with the user's approval of plan ruling R1: 5.4 step 4 states that `returned_type` is any genuine class, whatever its metaclass (it read "an exact `type` instance", which contradicted the step's "raises nothing"). Revision 4 adds the user's scoped clarifications: process-control exceptions propagate and their handling is SE-5's (5.4, 5.6, N5); `NO_STATE` serialization is SE-14/OD-20 (5.3, section 10); SE-5's derivation of a type name (5.6, section 11). Revision 3 fixes the scoped re-review of revision 2 (approved with changes: 1 MEDIUM, 2 LOW): a non-outcome is now returned as an engine value instead of raised, so a strategy cannot forge it. Revision 1 was reviewed by Opus (`slice-reviewer`: approved with changes, 2 HIGH, 4 MEDIUM, 3 LOW). The implementation findings are fixed in this revision; the three that needed the user were answered as U2 to U4 (section 12). Section 13 holds the domain changes that follow; they are approved or rejected together with this specification.  
**Domain references:** sections 3, 6.2, 6.4, 6.7, 6.8; DR-12, DR-22, DR-23, DR-25, DR-26; OD-13, OD-17, OD-19, OD-20 (none decided here; see sections 11 and 13)

Decisions marked **[user Un]** were given by the user in the SE-4 conversation (section 12). Everything marked "my call" is an implementation choice the builder may keep or improve without changing behavior. Names of modules, classes and functions are indicative; the behavior is what is specified.

## 1. Goal

The strategy side of an evaluation: strategy identity, the two contracts of section 6.4, and the evaluation of one stateless strategy for one evaluation context as a pure transition (DR-26), fully implemented and tested with test strategies. The stateful contract exists as a type only, so that later slices code against a fixed shape; nothing loads, passes or runs state (SE-14). Out of scope: execution over pairs, ordering, refused input, the report and the entry for a strategy that raises (SE-5); input declaration (SE-7a, OD-13); every real strategy (SE-12).

## 2. Why this shape

| Choice | Derivation |
|---|---|
| Identity is a value type holding `id` and `version`, each a non-empty exact `str` with no other rule | Section 6.4 ("no imposed format"); the same rule as the instrument key of SE-3 (spec 5.2), so no surrogate rule is added. |
| The two contracts are nominal abstract base classes, and a class cannot implement both | Section 6.4 names two contracts; execution must tell them apart without inspecting the strategy (my call: ABCs rather than structural protocols, so "which contract" is a type question). |
| A stateless strategy's evaluation takes only the context | DR-26, DR-12: the inputs are snapshot, parameters and `as_of`, all in the context (SE-3 spec 5.8); no mode flag, no instrument key (section 6.8). |
| The engine's stateless evaluation calls the strategy once and returns its outcome unchanged | DR-23 (signals are treated generically, never filtered, reordered or read); section 6.2 (the engine never sorts signals). |
| A returned value that is not exactly one of the three outcomes comes back as a distinct engine value, never as an exception; an exception from the strategy passes through unchanged | Section 6.7 gives both cases to execution, and under U3 their entries differ. Returning a value the strategy cannot forge keeps them apart: every exception out of the evaluation is the strategy's (my call, re-review finding M1). SE-4 reports nothing. |
| Absent state is a dedicated engine marker, not `None` | **[user U1]**. `None` stays a state value a strategy may choose. |
| `next_state` may also be the marker, meaning the strategy supplies no state | **[user U2]**, replacing the second half of U1. A first evaluation that fails then needs no invented state. What the engine does with it is OD-19 (SE-14). |
| A non-outcome return carries the returned value's type; a malformed identity is refused input | **[user U3]**, recorded in domain section 6.7 (section 13). Both are SE-5's to build; SE-4 only makes the first one available. |
| The engine never inspects a state value beyond telling the marker apart by identity | DR-25. |

## 3. Scope

1. Modules in `sentaris_engine.domain`. My call: `strategy` (identity, the two contracts, the absent-state marker, the stateful outcome type) and `evaluation` (stateless evaluation and its error). The plan may merge them.
2. One new value type for a result that is not an outcome (5.4). No new error class: malformed arguments to the SE-4 types and to the evaluation function raise SE-3's `EvaluationTypeError`.
3. Test strategies under `tests/` only. No module is added under `sentaris_engine.strategies`.
4. Tests, as listed in section 8.
5. `CLAUDE.md` "Current state" says that SE-4 exists.
6. The domain edits of section 13, only with the user's approval of this specification.

## 4. Dependencies

SE-3 is merged on `main` at `40189df` and `make check` passes (1345 tests). SE-4 has no gate. All modules are pure domain code. They import only `sentaris_engine.domain` and pinned pure-stdlib modules (expected: `abc`, `dataclasses`, `typing`). No architecture list is widened and no dependency is added. Tests may use non-pinned stdlib modules (`inspect`, `copy`), as SE-3's tests do.

## 5. Interfaces and contracts

The SE-3 rules apply to every new value type: exact types, immutable, final, and malformed input raises exactly `EvaluationTypeError` (SE-3 spec 5). The two contract classes are the exception to "final": strategies subclass them.

### 5.1 Strategy identity (section 6.4)

- `StrategyIdentity(id, version)`: each field a non-empty exact `str`. No format, length or surrogate rule (section 2). Anything else raises `EvaluationTypeError`.
- Equality and hash are by `(id, version)`; two identities with the same fields are equal. No ordering is defined here; the execution order of section 6.7 is SE-5's.
- Frozen and final.

### 5.2 The two contracts (section 6.4, DR-26)

- **`StatelessStrategy`**, an abstract base class with:
  - `identity`: a `StrategyIdentity`. My call: declared on the ABC so a subclass must provide it, as a class attribute or a property.
  - `evaluate(self, context) -> Result`, abstract. `context` is an `EvaluationContext`.
- **`StatefulStrategy`**, an abstract base class with:
  - `identity`, as above.
  - `evaluate(self, context, previous_state) -> StateTransition`, abstract. `previous_state` is either a state value or `NO_STATE` (5.3).
  - Nothing in SE-4 calls it (SE-14).
- A class that derives from both is refused when it is defined (`TypeError`, my call), so a strategy has exactly one contract.
- **Membership is real inheritance** (my call, review finding 1). A strategy follows a contract exactly when the contract class is in `type(strategy).__mro__`. `isinstance` is not used, because it accepts virtual subclasses and trusts a spoofed `__class__`. `register` on either contract raises `TypeError`, so no virtual subclass exists.
- The engine calls `evaluate` with positional arguments only, so a strategy's own parameter names do not matter (my call).
- Neither contract has any other abstract or required member, and neither method takes any further argument: no mode flag (DR-12), no instrument key (section 6.8), no clock or randomness source (DR-08).
- The contracts state the obligations of DR-26 and DR-22 in their docstrings by ID. Purity of a strategy is checked statically for the `strategies` package by SE-1's checks; a test strategy under `tests/` is not, and none of SE-4's guarantees relies on that.

### 5.3 Absent state (DR-25, U1, U2)

- `NO_STATE` is the single instance of a final marker class. As `previous_state` it stands for "no state recorded for the scope" (section 3, "Strategy state"); as `next_state` it stands for "the strategy supplies no state" (U2).
- It is not `None` and never equals `None`, `False`, `0`, `""`, or any other value but itself. It is hashable.
- There is only one: calling the marker class again returns `NO_STATE` or raises (my call: returns `NO_STATE`); `copy.copy` and `copy.deepcopy` return `NO_STATE` itself, so the identity check `previous_state is NO_STATE` survives any copying the engine or a strategy might do within one process.
- **Within one process only.** How absent state is serialized, stored and restored across a process boundary (pickling included) is not specified by SE-4 and is not tested; it belongs to SE-14 and OD-20 (state encoding). SE-4 adds no serialization support for the marker.
- It is not a payload value and not a parameter value (SE-2, SE-3 reject it already as an unknown type; a test pins that).
- How the engine tells lost or unreadable state from a first evaluation is OD-19 and is not decided by this marker; it only represents "absent".

### 5.4 Stateless evaluation (DR-26, DR-23, DR-22)

`evaluate_stateless(strategy, context) -> Result | NotAnOutcome`:

1. `strategy` must follow `StatelessStrategy` by real inheritance (5.2) and `context` must be an exact `EvaluationContext`. Otherwise it raises `EvaluationTypeError` without calling anything. Execution builds these arguments itself, so this refusal is a programming error of the caller, not a strategy outcome.
2. It calls `strategy.evaluate(context)` exactly once, positionally, passing the very context object it received.
3. If the returned value's type is exactly `Signals`, `NoSignal` or `EvaluationFailure` (SE-3 spec 5.5), it returns that very object, unchanged.
4. Otherwise it returns a new `NotAnOutcome(returned_type)` (scope item 2), where `returned_type` is `type(value)` of the returned value. It raises nothing. `NotAnOutcome` is frozen and final, is not one of the three outcomes and not a `Result`, and only the engine constructs it on this path. A strategy could construct one and return it; it is then itself a non-outcome, so the engine wraps it in a new `NotAnOutcome` whose `returned_type` is `NotAnOutcome`. A strategy therefore cannot make the engine report a type it did not return. `returned_type` must be a genuine class: its own type (`type(returned_type)`, never a claimed `__class__`) is `type` or a subclass of `type`, so a class with any metaclass is accepted; anything else raises `EvaluationTypeError`. The returned value itself is neither kept nor inspected beyond its type. Under U3 the entry SE-5 builds reports the name of `returned_type`. SE-4 holds the type object only and derives no name; how SE-5 derives one is bound by 5.6. This representation is SE-4's; SE-5 may change it as long as U3 holds (review finding 4).
5. Any exception raised by `strategy.evaluate`, of any class including `BaseException` subclasses, propagates unchanged: same object, not wrapped, not chained, and with its `__cause__` and `__context__` as the strategy left them. SE-4 classifies no exception: it catches nothing, so process-control exceptions (`KeyboardInterrupt`, `SystemExit`, and any other `BaseException` that is not an `Exception`) leave it exactly as ordinary ones do. Catching and reporting are SE-5's (section 6.7). Because a non-outcome is returned, not raised, every exception that leaves `evaluate_stateless` after step 1 is the strategy's.
6. It reads no identity, keeps nothing between calls, and has no other effect. It does not read `identity` at all; reading it once per execution is SE-5's (section 6.7).

### 5.5 Stateful outcome, type only (DR-26, DR-25, U2)

`StateTransition(result, next_state)`:

- `result`: exactly one of the three outcome types; anything else raises `EvaluationTypeError`. Note for SE-14: a stateful strategy that builds a transition with a non-outcome raises inside its own code, so for stateful strategies such a mistake reaches execution as a strategy raise, not as a non-outcome return.
- `next_state`: any value, `NO_STATE` included (U2). The value is held as given: not copied, frozen, validated or inspected (DR-25). `None` is accepted and is a state value, not absence.
- Frozen and final. Equality by identity (my call: `eq=False`), because comparing two transitions would compare opaque states, which the engine never does (DR-25).

### 5.6 Obligations handed to SE-5

These follow from section 6.7 and U3. SE-4 builds none of them and does not test them; they bind SE-5's specification, which brings the open parts to the user (section 11).

- **Process-control exceptions.** Section 6.7 catches "only ordinary exceptions"; "an interrupt or exit request propagates". SE-5 must state explicitly which classes it catches and must let `KeyboardInterrupt` and `SystemExit` propagate. It must never turn any exception into an evaluation failure, a "no signal" or a non-outcome entry: a caught exception becomes the separate entry of section 6.7 and nothing else. Which other `BaseException` subclasses count as "ordinary" is not stated by the domain document (section 11).
- **Type name of a non-outcome.** SE-5 derives the name from `NotAnOutcome.returned_type` alone. It never touches the returned value (SE-4 does not keep it), and it formats nothing from it: no `repr`, `str` or attribute of the value. It reads the name without running strategy-controlled code; a class's `__name__`, `__qualname__` and `__module__` can be overridden by a metaclass, so reading them through the class's own attributes is not enough on its own. Whether the reported name is the bare name or a module-qualified one, and therefore how two classes with the same name are told apart, is open (section 11). Whatever is chosen applies equally to the exception's type name of the same section, so the two kinds of entry name types the same way.

## 6. Expected behavior

- A test strategy that returns `NoSignal()` for every context gives `NoSignal()` through `evaluate_stateless`; the same for `Signals` and `EvaluationFailure`, each returned as the identical object.
- A strategy whose `Signals` holds kinds the engine has never seen, in an order that is not sorted, comes back with the same kinds in the same order (the same object).
- Evaluating one deterministic test strategy repeatedly on the same context gives equal results each time (DR-26). Evaluating it on two contexts built twice from the same constructor arguments (distinct objects with the same field values; contexts compare by identity, SE-3 spec 5.7) also gives equal results.
- A strategy returning `None`, a bare `Signal`, a `tuple` of signals, the class `NoSignal` instead of an instance, a `StateTransition`, `NO_STATE`, or a `NotAnOutcome` of its own makes `evaluate_stateless` return a new `NotAnOutcome` holding that value's type.
- A strategy raising `ValueError`, `EvaluationTypeError` or `KeyboardInterrupt` has that exact exception object propagate.
- Evaluating strategy A, then a strategy B that fails or raises, then A again gives A the same result as A alone (DR-22, as far as one evaluation call can show it; across pairs it is SE-5's).

## 7. Acceptance criteria

| AC | Criterion |
|---|---|
| AC-1 | `StrategyIdentity` accepts exactly two non-empty exact `str` fields and compares by them (N1). |
| AC-2 | The two contracts have exactly the members and method parameters of 5.2, and a class cannot take both (N2, N3). |
| AC-3 | `NO_STATE` behaves as 5.3 (N10). |
| AC-4 | `evaluate_stateless` returns the strategy's outcome unchanged (N7, N8), returns a `NotAnOutcome` for a non-outcome and never raises for it (N4), lets every strategy exception through unchanged (N5), and refuses malformed arguments without calling the strategy (N6). |
| AC-5 | Repeated evaluation is identical, and the determinism check used by the tests detects a strategy that is not (N7). |
| AC-6 | An evaluation is unaffected by evaluations of other strategies before it (N9). |
| AC-7 | `StateTransition` behaves as 5.5 (N11). |
| AC-8 | No new value type can be subclassed or have a field reassigned (N12). |
| AC-9 | `make check` passes, and the new modules fall under the SE-1 purity checks without any list being widened. |

## 8. Negative tests

Names are indicative; the plan fixes them. Rejection tests assert the exception class only, with `type(exc) is ...`.

| # | Rule | Test | Fails when |
|---|---|---|---|
| N1 | Section 6.4 | `test_invalid_strategy_identity_is_refused`: `id` or `version` given as `""`, `None`, `1`, `b"x"`, a `str` subclass instance. Positive companion: values with spaces and with a surrogate are accepted, and two identities with the same fields are equal and hash equal. | any is accepted, a different error class escapes, or equal fields compare unequal |
| N2 | DR-12, DR-26, section 6.8 | `test_contract_signatures_take_only_the_transition_inputs`: `inspect.signature` of `StatelessStrategy.evaluate` is exactly `(self, context)`, of `StatefulStrategy.evaluate` exactly `(self, context, previous_state)`, of `evaluate_stateless` exactly `(strategy, context)`; the set of abstract members of each contract is exactly `{identity, evaluate}`. | a parameter or abstract member is added or removed |
| N3 | Section 6.4 | `test_strategy_cannot_take_both_contracts`: defining a class deriving from both raises `TypeError`; `register` on either contract raises `TypeError`. `test_contract_requires_evaluate_and_identity`: a subclass missing either cannot be instantiated. | any succeeds |
| N4 | Section 6.7 (made distinguishable), U3, section 6.2 | `test_non_outcome_result_is_reported_as_value`, parametrised over a test strategy returning `None`, a `Signal`, a `tuple` of `Signal`, a `list`, the class `NoSignal`, a `StateTransition`, `NO_STATE`, an exception instance, `True`, and a `NotAnOutcome(int)` it built itself. Returns, without raising, an exact `NotAnOutcome` whose `returned_type` is exactly the returned value's type (for the self-built case: `NotAnOutcome`, not `int`), and which is a new object, not the strategy's. `test_not_an_outcome_is_validated`: a `returned_type` that is not a `type` (`None`, `"int"`, `1`) raises exactly `EvaluationTypeError`. | accepted as an outcome, an exception raised, the wrong type held, or the strategy's own value passed through |
| N5 | Section 6.7 (left to execution) | `test_strategy_exception_propagates_unchanged`: for `ValueError`, `EvaluationTypeError`, `KeyboardInterrupt`, `SystemExit` and a test-defined direct `BaseException` subclass raised by the strategy, the caught object is the raised object, and its `__cause__` and `__context__` are what the strategy left. | swallowed, wrapped, replaced or chained |
| N6 | Section 5.4 | `test_malformed_evaluation_arguments_are_refused`: `strategy` as a `StatefulStrategy` instance, a plain object with an `evaluate` method, a function, `None`, an object whose `__class__` property claims `StatelessStrategy`; `context` as `None`, a `Snapshot`, a `dict`. Raises exactly `EvaluationTypeError`, and a recording test strategy shows it was not called. | accepted, the strategy is called, or another class raised |
| N7 | DR-26 | `test_repeated_stateless_evaluation_is_identical`, parametrised over a deterministic test strategy for each of the three outcomes: N evaluations on one context, and on two contexts built from the same constructor arguments (section 6), give equal results. `test_determinism_check_detects_a_varying_strategy`: the determinism check used above fails for a test strategy whose result changes from call to call. | results differ, or the check passes a varying strategy |
| N8 | DR-23, section 6.2 | `test_outcome_is_returned_unchanged`: the returned object `is` the strategy's; for `Signals` with unknown kinds in descending kind order, the signals tuple is the same object and in the same order. | anything is filtered, rebuilt, reordered or replaced |
| N9 | DR-22 | `test_evaluation_is_independent_of_other_strategies`: A alone; then A after B returning a failure, after B raising (caught by the test) and after B returning a non-outcome; A's results are equal in every case, and A receives the very context object passed in. | A's result changes |
| N10 | DR-25, U1, U2 | `test_no_state_marker`: `NO_STATE is not None`; it is unequal to `None`, `False`, `0`, `""`, `()`; calling its class returns it; `copy.copy` and `copy.deepcopy` return it; the class cannot be subclassed; it is refused as a payload value and as a parameter value. | any of these fails |
| N11 | DR-25, U2 | `test_state_transition`: a non-outcome `result` (the same cases as N4) raises exactly `EvaluationTypeError`; `next_state` as `NO_STATE`, `None`, a `dict` and `object()` is accepted and held as the identical object (not copied); fields cannot be reassigned. | a non-outcome is accepted, the marker is refused, or the state is copied or altered |
| N12 | Section 5 | `test_new_types_are_final_and_frozen`: `StrategyIdentity`, `StateTransition`, `NotAnOutcome` and the marker class cannot be subclassed; no field of the first three can be reassigned; no attribute can be set on `NO_STATE` | a subclass can be defined, a field reassigned, or an attribute set on the marker |

## 9. Enforced guarantees and known limitations

After this slice, the tests above enforce:

- the identity shape of section 6.4 (N1);
- that the contracts themselves take only the inputs of DR-26, with no mode flag or instrument key (section 6.8) (N2). This is the contract's part of DR-12, not DR-12 for strategies;
- one contract per strategy (N3);
- that the engine's stateless evaluation passes the outcome through untouched (DR-23, section 6.2; N8);
- that it is deterministic for a deterministic strategy (DR-26, N7);
- that one evaluation call carries nothing from another (DR-22, N9);
- the absent-state marker and the stateful outcome shape (U1, U2; N10, N11).

U3 (section 6.7 as amended) is not enforced by SE-4: it is SE-5's. N4 shows only that the returned type is available to it.

These remain convention or review only:

- **Purity of a strategy itself** (DR-08, DR-26). The engine cannot prove that a strategy is pure. It is checked statically for code under `sentaris_engine.strategies` (SE-1), and by review. N7 shows determinism only for the test strategies.
- **DR-12 inside a strategy.** A concrete strategy could still declare an extra defaulted parameter (`evaluate(self, context, live=False)`) or branch on a mode by other means; the engine calls it positionally with the context alone, so such a flag never receives a value from the engine, but nothing detects it. Review only.
- **The engine never reads a payload** (DR-23). N8 shows that the outcome object is returned untouched; that no engine code reads a payload in between is review.
- **DR-25, never inspecting state.** `StateTransition` holds the state without touching it (N11); SE-14 is where state handling is built and checked.
- **A strategy that raises `EvaluationTypeError` itself** looks like the engine refusing its arguments (5.4 step 1). Execution constructs the arguments itself, so a refusal there is a bug in execution code, not a pair's outcome; SE-5 must not call `evaluate_stateless` with arguments it has not built as 5.4 requires. A non-outcome cannot be confused with a raise, because it is returned (5.4 step 4, N4).
- **Calling `__init__` again** on an existing dataclass instance, and reachability through private attributes, as in SE-3 section 9.

## 10. Exclusions

- Execution over pairs, ordering, duplicate and identity refusal, catching exceptions, the report and its entries (SE-5).
- Malformed parameters in execution (SE-5b, OD-3).
- Loading, passing, persisting state; running a stateful transition; continuity (SE-14, OD-17, OD-19, OD-20). This includes serializing and restoring `NO_STATE` across a process boundary (5.3).
- Deriving and reporting type names, and deciding which exceptions are caught (SE-5; 5.6).
- Input declaration (SE-7a, OD-13).
- Any real strategy (SE-12).
- No change to `docs/domain.md` beyond section 13, and none at all without the user's approval. No change to `docs/roadmap.md`.

## 11. Open questions

None blocks SE-4. Recorded for the decisions that own them; none is decided here:

1. **OD-19: an absent `next_state`.** Under U2 a stateful strategy may return `NO_STATE` as `next_state`. Whether that keeps the previous state, clears it, or is refused is OD-19 (section 13 adds it there).
2. **OD-20: constraints on state values.** SE-4 accepts any object as state. Whether state must be immutable, encodable or bounded is OD-20, and so is how `NO_STATE` is encoded and restored.
3. **For SE-5: which exceptions are "ordinary".** Section 6.7 names an interrupt and an exit request as propagating. Whether every other `BaseException` that is not an `Exception` (for example `GeneratorExit`, or a strategy-defined one) is caught or propagates is not stated. To be brought to the user with SE-5's specification (5.6).
4. **For SE-5: the form of a reported type name.** Section 6.7 and U3 say "type name". A bare name is ambiguous between two classes of the same name in different modules; a module-qualified name is not, but is longer and names the strategy's modules. Which one is reported, for exceptions and non-outcomes alike, is not stated. To be brought to the user with SE-5's specification (5.6).

## 12. Decisions by the user (2026-11-13)

- **U1.** In the stateful contract, `previous_state` is an opaque value or a dedicated engine marker for absent state, not `None`, so `None` stays a valid state. Neither decides OD-19 nor OD-20. (U1's second half, "the marker is not a valid `next_state`", is replaced by U2.)
- **U2.** In answer to the specification review: `next_state` may also be the marker, meaning the strategy supplies no state, so a first evaluation that fails needs no invented state. What the engine does with it stays OD-19.
- **U3.** Two gaps in domain section 6.7 found by the review are decided now, so that SE-5 stays without a gate: (a) for a result that is not one of the three outcomes, the separate entry carries the type name of the returned value, never the value; (b) a strategy whose identity cannot be read, or is not an `id` and a `version` as section 6.4 requires, is refused for the whole execution before anything runs.
- **U4.** U1 and U2 are recorded in domain section 6.4, as SE-3's U5 was recorded in section 6.5 (section 13).

## 13. Proposed document changes (need the user's approval)

Each edit replaces the quoted "before" text by the "after" text in `docs/domain.md`; nothing else in the document changes. They alter no established rule (section 4) and no decision of section 6 beyond adding U2 to U4. `docs/roadmap.md` and `CLAUDE.md` need no change for them: SE-5's row already cites section 6.7, and Phase A stays without gates. The edits are made in the first task of the SE-4 plan. If the user does not approve them, none is made.

1. Section 6.4 heading. Before: `### 6.4 Strategy contract (part of OD-13, 2026-11-10)`. After: `### 6.4 Strategy contract (part of OD-13, 2026-11-10; amended 2026-11-13)`.
2. Section 6.4, a new bullet directly after the bullet that begins `- There are two contracts, one per form in DR-26:`. The new bullet:
   ```text
   - In the stateful contract, absent state is a dedicated value, distinct from every state value, null included. `previous_state` is absent when no state has been recorded for the scope; a strategy may return absent as its `next_state` to supply no state. What an absent `next_state` leaves behind is open (OD-19).
   ```
3. Section 6.7 heading. Before: `### 6.7 Execution over several strategies and instruments (OD-15 and OD-26, 2026-11-11)`. After: `### 6.7 Execution over several strategies and instruments (OD-15 and OD-26, 2026-11-11; amended 2026-11-13)`.
4. Section 6.7, "Refused input" bullet. Before: `A strategy's identity is read once per execution.` After:
   ```text
   A strategy's identity is read once per execution; a strategy whose identity cannot be read, or does not consist of an `id` and a `version` as section 6.4 requires, is refused for the whole execution before anything runs.
   ```
5. Section 6.7, "A strategy that raises" bullet. Before: `because a message may carry data of the strategy's context.` After: `because a message may carry data of the strategy's context. For a result that is not one of the three outcomes, the type name is that of the returned value, and the value itself is never reported.`
6. Section 7, OD-19 row. Insert ``what an absent `next_state` (section 6.4) leaves behind; `` directly before ``what state a strategy that raises leaves behind (section 6.7);``. The row then begins:
   ```text
   | OD-19 | **State on failure and continuity.** What state an evaluation failure leaves behind (the previous state kept, or a strategy-supplied `next_state`); what an absent `next_state` (section 6.4) leaves behind; what state a strategy that raises leaves behind (section 6.7); …
   ```

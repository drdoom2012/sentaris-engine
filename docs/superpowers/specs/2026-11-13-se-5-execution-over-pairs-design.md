# SE-5 — Execution over pairs: design

**Slice:** SE-5 (`docs/roadmap.md`, Phase A)  
**Status:** Revision 4, approved by the user together with section 13 (2026-11-13). The section 13 edits are made in the first task of the plan. Revision 4 adds the user's two scoped clarifications: engine-level pair isolation does not extend to state a strategy keeps itself (5.3 step 7, AC-8, section 9), and the type-name guarantee of 5.5 names the class-dict hash-collision limitation of section 9. Revision 3 fixes the scoped re-review of revision 2 (approved with changes: 1 MEDIUM, 3 LOW; none needed the user). Revision 1 was reviewed by Opus (`slice-reviewer`: approved with changes; 1 CRITICAL, 1 HIGH, 4 MEDIUM, 5 LOW). The three findings that needed the user were answered as U7 to U9 (section 12); the others are fixed in this revision. The CPython behavior behind F2 (a `str`-subclass `__qualname__`, a missing or non-`str` `__module__`, an empty qualname) was confirmed by a probe on Python 3.12.  
**Domain references:** sections 3 ("Strategy execution"), 6.2, 6.4, 6.5, 6.6, 6.7, 6.8; DR-09, DR-10, DR-13, DR-14, DR-22, DR-27; OD-3, OD-13, OD-17 to OD-20 (none decided here; see sections 11 and 13)

Decisions marked **[user Un]** were given by the user in the SE-5 conversation (section 12). Everything marked "my call" is an implementation choice the builder may keep or improve without changing behavior. Names of modules, classes and functions are indicative; the behavior is what is specified.

## 1. Goal

One execution for one `as_of` over an explicit list of (stateless strategy, instrument) pairs, each with its own parameters, given one prebuilt snapshot per instrument (section 6.7). It refuses malformed input as a whole before anything runs, evaluates the pairs one after another in the decided order, isolates a strategy that raises or returns a non-outcome to its own pair, and returns a report with one entry per pair. Stateless pairs only (SE-14 adds state). Out of scope: building snapshots (SE-7b), malformed parameters as a per-pair failure (SE-5b, OD-3), what the pairs of an instrument report when its snapshot cannot be built (SE-10, OD-3).

## 2. Why this shape

| Choice | Derivation |
|---|---|
| Execution receives prebuilt snapshots keyed by instrument key | Roadmap SE-5 row ("one prebuilt snapshot per instrument"); building them is SE-7b. |
| Pairs are sorted by `(instrument, id, version)` by code point, and the report keeps that order | Section 6.7 "Order"; DR-10. Python `str` comparison is by code point. |
| Every refusal happens before any strategy is evaluated, and refuses the whole execution | Section 6.7 "Refused input" (duplicates, keys, identity); **[user U3]**, **[user U5]**, **[user U6]**, **[user U8]** for the other inputs. An empty list is valid **[user U7]**. |
| Only `Exception` is caught | **[user U1]**. |
| A reported type name is module-qualified | **[user U2]**. |
| A fault entry says whether the strategy raised or returned a non-outcome | **[user U4]**. |
| A pair's parameters are an already built `Parameters` | **[user U6]**. Malformed parameters cannot reach SE-5's execution; SE-5b adds the per-pair path of section 6.5. |
| Execution lives in `sentaris_engine.application` | My call. It is a use case composed of domain operations (SE-4's `evaluate_stateless`); the domain keeps the types and rules. `application` is under the same SE-1 purity checks as `domain`, and may import `domain`. |

## 3. Scope

1. A module `sentaris_engine.application.execution` (my call) with the pair type, the report types, the refusal error and the execution function.
2. Tests under `tests/application/`, with test strategies under `tests/` only. No module is added under `sentaris_engine.strategies`.
3. `CLAUDE.md` "Current state" says that SE-5 exists.
4. The domain edits of section 13, only with the user's approval of this specification.

## 4. Dependencies

SE-4 is merged on `main` at `e0498bd` and `make check` passes (1441 tests). SE-5 has no gate. The new module imports only `sentaris_engine.domain` and pinned pure-stdlib modules (expected: `dataclasses`, `enum`, `typing`). No architecture list is widened and no dependency is added.

## 5. Interfaces and contracts

The SE-3 rules apply to every new value type: exact types, immutable, final, and malformed input to a constructor raises exactly `EvaluationTypeError` (SE-3 spec 5).

### 5.1 Pair

`Pair(instrument, strategy, parameters)`:

- `instrument`: an instrument key, checked with SE-3's `check_instrument_key` (section 6.8). Anything else raises `EvaluationTypeError`.
- `parameters`: an exact `Parameters` (SE-3), else `EvaluationTypeError` **[user U6]**.
- `strategy`: held as given and not checked here. Its contract and identity are execution's, because the identity is read once per execution (section 6.7, 5.3). Reading nothing of the strategy keeps strategy code from running when a pair is built.
- Frozen and final. Equality by identity (my call: `eq=False`), since a pair holds a strategy object, which the engine never compares. The `strategy` field is excluded from the `repr` (`repr=False`), because `repr(strategy)` is strategy code (review F8).

An invalid instrument key is therefore refused before the execution is called. That is still "before anything runs" (section 6.7); the refusal comes from the pair, not the execution (my call, so that a pair is valid by construction, as SE-3's types are).

### 5.2 Report types

- **`StrategyFault(cause, type_name)`**: the separate result type of section 6.7, distinct from the three outcomes of DR-14 and not a `Result`.
  - `cause`: one member of a final enum `FaultCause` with exactly two members, `RAISED` and `RETURNED_NON_OUTCOME` **[user U4]**.
  - `type_name`: an exact `str`, derived as in 5.5. It may be empty: a class's qualname can be `""` and records no usable module, and the name is never invented **[user U9]**. No surrogate rule (my call: a class name may hold anything a `str` holds; see section 11, question 1).
  - It never carries an exception message, an exception object, a traceback, the returned value or anything formatted from either.
- **`ReportEntry(instrument, strategy, outcome)`**: `instrument` an instrument key; `strategy` an exact `StrategyIdentity` (the one read for the execution, 5.3); `outcome` exactly one of `Signals`, `NoSignal`, `EvaluationFailure` or `StrategyFault`.
- **`ExecutionReport(as_of, entries)`**: `as_of` an instant (`check_instant`); `entries` an exact `tuple` of exact `ReportEntry`. No other field: no wall-clock time, run id or duration (DR-09).
- All three are frozen and final, and compare by their fields. An entry therefore compares equal exactly when its instrument, identity and outcome do, with signals compared by canonical form (section 6.3).

### 5.3 Execution

`execute(as_of, pairs, snapshots) -> ExecutionReport`. The steps run in this order. Steps 1 to 3, 5 and 6 run no strategy code; step 4 runs only the `identity` reads. Any refusal raises `ExecutionRefusedError` (5.4) and evaluates nothing.

1. **Shapes.** `as_of` passes `check_instant`. `pairs` is an exact `tuple` of exact `Pair`. `snapshots` is an exact `dict`; each key is checked with `check_instrument_key` and each value is an exact `Snapshot` before any set of keys is built or compared, so no hash or equality of a foreign object runs (review builder question 5). A pair's `instrument` is trusted as validated by `Pair` (5.1). An empty `pairs` is accepted with an empty `snapshots` and gives a report with no entries **[user U7]**.
2. **Snapshots** **[user U5]**, **[user U8]**. The set of snapshot keys equals the set of the pairs' instruments: a missing snapshot and a surplus snapshot are both refused. Every snapshot's `as_of` equals the execution's `as_of`. No snapshot object appears under two keys, compared by object identity (`is`), never by equality (section 6.7: "pairs of different instruments share nothing").
3. **Contract** **[user U3]**. For every pair, before any identity is read, the strategy must follow `StatelessStrategy` and not `StatefulStrategy`, judged by the real MRO of its real type: the MRO is read with `type`'s own `__mro__` descriptor applied to `type(strategy)`, never through the class or its metaclass, and every MRO entry is compared with the two contract roots by object identity (`is`), never with `==` or `in`, which would run a metaclass `__eq__` (review F4). Exactly one root must occur, and it must be `StatelessStrategy` (SE-4 report F2). A stateful strategy, an object of neither contract, an object whose `__class__` claims a contract, and a class holding both roots are refused (SE-14 will admit stateful pairs). The identity of a refused strategy is never read.
4. **Identity** (section 6.7, SE-4 U3). Each strategy object's `identity` is read exactly once per execution, even when that object is in several pairs. Objects are told apart by `id(strategy)` while `pairs` keeps them alive, never by hashing or comparing them, since `__hash__` and `__eq__` are strategy code (review F9). The read value must be an exact `StrategyIdentity` (section 6.4), and its two fields, read from that exact final type, must each be a non-empty exact `str`. The engine then builds its own new `StrategyIdentity(id, version)` from those two strings and uses only that copy for duplicates, sorting and the report, so a strategy that keeps and later mutates its identity object changes nothing the engine holds (review F3). If reading raises an `Exception`, or the value or a field is anything else, the execution is refused. The strategy's exception is attached as `__cause__` of the refusal (my call: a refusal goes to the composition root, not into a report, so section 6.7's message rule for entries does not apply; no context exists yet at this point). An exception that is not an `Exception` propagates unchanged (U1). Identities are read in the order of `pairs` (my call); it affects nothing but which refusal is raised first.
5. **Duplicates.** Two pairs with the same `(instrument, id, version)` refuse the execution (section 6.7).
6. **Order.** The pairs are sorted ascending by `(instrument, id, version)`, each compared as an exact `str` by code point (section 6.7, DR-10). Because every element is an exact `str` the engine holds (steps 1 and 4), sorting runs no foreign code. The input order of `pairs` and the insertion order of `snapshots` affect nothing.
7. **Evaluation**, one pair after another, never concurrently (section 6.7). For each pair, a new `EvaluationContext(snapshot, parameters, as_of)` is built from that instrument's snapshot object (the very object given, shared by all pairs of that instrument, never copied), the pair's own `Parameters` object and the execution's `as_of`. The context is built outside the `try`, so an engine bug is never reported as a strategy fault; the `try` wraps only the call of SE-4's `evaluate_stateless`, made once with the strategy and that context (review builder question 4).
   - A returned outcome becomes the entry's outcome, as the very object (DR-23).
   - A returned `NotAnOutcome` becomes `StrategyFault(RETURNED_NON_OUTCOME, name)` from its `returned_type` (5.5).
   - An `Exception` raised out of the call becomes `StrategyFault(RAISED, name)` from the exception's real type, `type(exc)` (5.5). The exception object is dropped. Because execution builds the arguments exactly as SE-4 spec 5.4 step 1 requires, every exception out of the call is the strategy's (SE-4 spec section 9).
   - Any other exception (`BaseException` that is not an `Exception`: `KeyboardInterrupt`, `SystemExit`, `GeneratorExit`, or a strategy-defined one) propagates unchanged: same object, not wrapped or chained. The execution ends there and returns no report **[user U1]**.
   - Execution carries nothing of one pair to the next: no engine-held value of one pair, its fault or failure included, reaches another pair's context or entry (DR-22). State a strategy keeps outside the engine is not in the engine's control (section 9).
8. **Report.** One entry per pair, in the order of step 6, each carrying the pair's instrument key and the engine's copy of the identity from step 4.

Execution reads no payload, parameter value or state (DR-23, section 6.5, DR-25), reads no clock, and keeps nothing between calls.

### 5.4 Refusal error

`ExecutionRefusedError`, a new class (my call: a subclass of `ValueError`, not of `EvaluationTypeError`, so that a caller can tell a refused execution from a malformed value type). Only the class is meaningful; a test asserts the class, never the message. A refusal message formats no strategy, key, snapshot or other caller value (review F8).

Chaining (my call, review F7 and builder question 6): a refusal caused by the strategy's `identity` raising has that exception as `__cause__` (step 4). Every other refusal, an `EvaluationTypeError` from `check_instant` or `check_instrument_key` included, is raised `from None`: it is the engine's own judgment of the input, and the class says all there is.

A malformed `Pair` or report value raises `EvaluationTypeError` from its constructor, as every SE-3 type does.

### 5.5 Type name **[user U2]**

The name of a class `cls` is the name of the module the type records, a `.`, and its qualname; a type that records no usable module is named by its qualname alone **[user U9]**. The derivation never raises and runs no strategy code, with one exception: the contrived class-dict hash collision accepted in section 9, where a planted key's `__eq__` runs and anything it raises leaves `execute` (review F2, re-review R2).

- **Qualname.** Read with `type`'s own `__qualname__` descriptor applied to `cls`, never through `cls`'s attributes or its metaclass (a metaclass can override `__name__`, `__qualname__` and `__module__`, SE-4 spec 5.6). CPython stores it as a `str`, possibly a `str` subclass; it is converted to an exact `str` with `str.__str__`, which runs no method of the subclass. It may be `""`.
- **Module.** Read with `type`'s own `__module__` descriptor applied to `cls`. For a heap type that descriptor reads the class's own dict and runs no descriptor found there; it raises `AttributeError` when the class records no `__module__`, and returns whatever a class body assigned otherwise. When the value's real type is `str` or a subclass of it (judged on `type(value)`, not by `isinstance`), it is first converted with `str.__str__`, and only that exact `str` is tested for emptiness, so no `__len__`, `__bool__` or `__eq__` of a subclass runs (re-review R1). The module is usable when the converted text is non-empty. An `AttributeError` from the descriptor, or any other value (`42`, a `property`, `None`), means no usable module.
- The parts are joined only after both are exact `str`, so no reflected `__radd__` of a subclass runs.
- Built-in types are named the same way, for example `builtins.NoneType`.

The same derivation names the exception type of a raise and the returned type of a non-outcome, so both kinds of entry name types the same way (SE-4 spec 5.6).

## 6. Expected behavior

- Three test strategies on two instruments, given in reverse order, produce entries in ascending `(instrument, id, version)` order, and the strategies are called in that order.
- Instrument keys `"B"`, `"a"`, `"￿"` and `"\U00010000"` sort as `"B" < "a" < "￿" < "\U00010000"` (code point, not case-folded, not UTF-16).
- The same strategy object paired with two instruments is evaluated twice, once per instrument, and its identity is read once.
- A strategy raising `ValueError("secret")` on one instrument gives that pair `StrategyFault(RAISED, "builtins.ValueError")`; the same strategy on another instrument and every other pair are evaluated normally, and `"secret"` appears nowhere in the report.
- A strategy returning `None` gives `StrategyFault(RETURNED_NON_OUTCOME, "builtins.NoneType")`.
- A strategy raising `KeyboardInterrupt` ends the execution with that exception object; no report is returned.
- A stateful strategy in the list, a duplicate triple, a missing or surplus snapshot, a snapshot of another `as_of`, or one snapshot object under two keys raises `ExecutionRefusedError` and no strategy is called.
- An execution of no pairs and no snapshots returns a report with no entries.
- Running the same execution twice, and running each pair alone, gives equal entries (DR-13, DR-22).

## 7. Acceptance criteria

| AC | Criterion |
|---|---|
| AC-1 | Pairs run and are reported in `(instrument, id, version)` code-point order, independent of input order (N1). |
| AC-2 | Every refused input of section 6.7 and of U3, U5, U8 refuses the whole execution before any strategy is evaluated; an empty execution gives an empty report (U7) (N2 to N5). |
| AC-3 | A strategy's identity is read exactly once per execution per strategy object, before any evaluation (N4). |
| AC-4 | An `Exception` from a strategy becomes a `RAISED` fault entry for that pair only; a non-outcome becomes a `RETURNED_NON_OUTCOME` fault entry; neither carries a message or value (N6, N7). |
| AC-5 | A `BaseException` that is not an `Exception` propagates unchanged (N8). |
| AC-6 | Type names are module-qualified and are read without running strategy code (N9). |
| AC-7 | Each pair's context holds its instrument's very snapshot, its own parameters and the execution's `as_of` (N10). |
| AC-8 | For strategies that keep no mutable state outside the engine, as the test strategies of N11 do, an entry is the same whether its pair runs alone or with others, and repeated executions are equal (N11). This is the engine's part of DR-22; independence of state a strategy shares behind the engine's back is not claimed (section 9). |
| AC-9 | `Pair` refuses an invalid key and non-`Parameters` parameters; the new types are validated, final and frozen (N12, N13). |
| AC-10 | `make check` passes, and the new module falls under the SE-1 purity checks without any list being widened. |

## 8. Negative tests

Names are indicative; the plan fixes them. Rejection tests assert the exception class only, with `type(exc) is ...`. "Nothing runs" is shown by a recording test strategy that logs every `evaluate` call.

| # | Rule | Test | Fails when |
|---|---|---|---|
| N1 | Section 6.7 "Order", DR-10 | `test_pairs_run_in_code_point_order`: every permutation of four pairs (two instruments, two identities differing in `id` and in `version`), with the snapshot `dict` built in different insertion orders, gives the same report and the same call log; the key set of section 6 sorts by code point. | the report or call order depends on input order, or sorting is not by code point |
| N2 | Section 6.7 "Refused input" | `test_duplicate_pair_is_refused`: two pairs with the same instrument and equal identities (same object, and two different objects with equal identities) raise `ExecutionRefusedError`; nothing runs. Positive companion: same identity on two instruments, and same instrument with two versions, are accepted. | accepted, or anything runs |
| N3 | Section 6.7, U3 | `test_strategy_of_wrong_contract_is_refused`: a `StatefulStrategy`, a plain object with `identity` and `evaluate`, an object whose `__class__` property claims `StatelessStrategy`, and a class made with both roots by bypassing the contract metaclass's `__new__` (SE-4 F2) raise `ExecutionRefusedError`; nothing runs, no identity of any pair is read, also when the wrong pair would sort last. A stateless strategy whose metaclass `__eq__` raises is accepted and its `__eq__` never runs (review F4). | accepted, an identity read, a metaclass `__eq__` run, or anything runs |
| N4 | Section 6.7, U3 | `test_identity_is_read_once_and_checked`: a counting `identity` property shows one read per strategy object per execution, also when the object is in three pairs, and that all reads precede the first `evaluate`. An `identity` that raises `ValueError`, or returns `None`, a tuple `("id", "1")` or an object whose `__class__` property claims `StrategyIdentity`, raises `ExecutionRefusedError` with the `ValueError` as `__cause__`; nothing runs. A `StrategyIdentity` whose `id` was changed with `object.__setattr__` to `""`, `1` or a `str` subclass before it is returned is refused. A strategy that keeps its identity object and mutates it during its `evaluate` leaves every entry of the report with the identity as read. A strategy whose `__hash__` and `__eq__` raise is read once and evaluated normally (review F3, F9). An `identity` raising `KeyboardInterrupt` lets it propagate unchanged. | read more or less than once, read after an evaluation, a bad or mutated identity accepted or reported, a strategy hashed or compared, or anything runs |
| N5 | U5, U7, U8, section 6.7 "One `as_of`", "Snapshot" | `test_snapshot_mismatch_is_refused`: a missing snapshot, a surplus snapshot, a snapshot whose `as_of` differs from the execution's, one snapshot object under two keys, a non-`Snapshot` value, a non-`dict` container, an invalid key in it (`""`, `1`, a `str` subclass whose `__hash__` and `__eq__` raise), `pairs` as a `list` or holding a non-`Pair`, and an execution `as_of` of `-1`, `True`, `2**53` or `1.0` raise `ExecutionRefusedError` with no `__cause__` (raised `from None`); nothing runs. Positive companions: empty `pairs` with empty `snapshots` gives a report with no entries (U7); two distinct snapshot objects with equal content under two keys are accepted. | accepted, a foreign `__hash__` or `__eq__` run, chained, or anything runs |
| N6 | Section 6.7 "A strategy that raises", DR-22, U1, U2, U4 | `test_strategy_exception_is_isolated_to_its_pair`: for `ValueError`, `EvaluationTypeError`, `RecursionError` and a test-defined `Exception` subclass whose message holds a sentinel, the raising pair's entry is exactly `StrategyFault(RAISED, "<module>.<qualname>")`; the same strategy on another instrument and the other pairs have the entries they have alone; the sentinel appears in no field and in the `repr` of no report object. | not caught, caught as a failure or "no signal", wrong name, a message leaks, or another entry changes |
| N7 | Section 6.7, U3 (a), U4 | `test_non_outcome_is_reported_as_fault`: for a strategy returning `None`, a `Signal`, a `list`, the class `NoSignal` and a `NotAnOutcome` of its own, the entry is exactly `StrategyFault(RETURNED_NON_OUTCOME, name of the returned type)`, and nothing of the value is kept. | reported as an outcome, as `RAISED`, with the wrong name, or the value kept |
| N8 | Section 6.7, U1 | `test_non_ordinary_exception_propagates`: `KeyboardInterrupt`, `SystemExit`, `GeneratorExit` and a test-defined direct `BaseException` subclass raised by a strategy leave `execute` as the same object, not chained, and no later pair runs. | caught, wrapped or chained, or a later pair runs |
| N9 | U2, SE-4 spec 5.6 | `test_type_name_is_module_qualified_and_safe`: a nested class gives `module.Outer.Inner`; two classes with the same `__name__` in different modules give different names; a metaclass whose `__getattribute__` raises or lies for `__name__`, `__qualname__` and `__module__` gives the real name and runs none of it; a class whose `__qualname__` is a `str` subclass with a recording `__radd__` and `__str__` gives the plain text and runs neither; a class whose `__module__` is a `str` subclass with recording `__len__`, `__bool__`, `__eq__` and `__str__` gives `module.qualname` with the plain text and runs none of them; a class whose `__module__` is `42`, a `property`, `""`, or absent (made by `type(...)` under `exec` with globals that have no `__name__`) gives its qualname alone; a class whose qualname is `""` and records no usable module gives `""`. Each case is checked both as a raised exception's type and as a returned value's type, and the execution always returns a report. | a bare name, an overridden attribute read, strategy code run, a crash, or no report |
| N10 | Section 6.7 "Snapshot", section 6.8 | `test_context_per_pair`: a recording strategy sees, for each pair, a context whose snapshot `is` its instrument's given snapshot, whose parameters `is` the pair's, and whose `as_of` is the execution's; two pairs of one instrument see the same snapshot object; no context holds an instrument key. | a copied or wrong snapshot, wrong parameters, or a key reaches the strategy |
| N11 | DR-22, DR-13, section 6.7 "Report" | `test_entry_is_the_same_alone_and_together`: each pair's entry from a mixed execution (signals, no signal, failure, raise, non-outcome) equals its entry when executed alone; two runs of the same execution give equal reports. | an entry depends on its neighbours or on the run |
| N12 | Section 6.8, U6 | `test_pair_is_validated`: `instrument` as `""`, `None`, `1`, a `str` subclass instance; `parameters` as a `dict`, `None`, a `FrozenMapping`, raise exactly `EvaluationTypeError`; the strategy is not touched (a strategy whose every attribute access raises is accepted by `Pair`). | accepted, another class raised, or the strategy touched |
| N13 | Section 5.2 | `test_report_types_are_validated_final_and_frozen`: `StrategyFault`, `ReportEntry`, `ExecutionReport` reject wrong field types (an outcome that is a `NotAnOutcome` or `None`, a `type_name` of `None` or a `str` subclass instance, a non-`FaultCause` cause, a `strategy` that is not an exact `StrategyIdentity`, entries as a `list`) with `EvaluationTypeError`; a `type_name` of `""` is accepted (U9); they and `Pair` cannot be subclassed or have a field reassigned; `repr` of a `Pair` does not call `repr` of its strategy (F8); `FaultCause` has exactly two members and cannot be extended. | any is accepted or can be changed, or a strategy's `repr` runs |

## 9. Enforced guarantees and known limitations

After this slice, the tests above enforce:

- the execution order and its independence from input order (section 6.7, DR-10; N1);
- refusal of duplicate pairs, invalid keys and identities, and wrong contracts before anything runs (section 6.7; N2 to N4, N12);
- isolation of a raising strategy or a non-outcome to its own pair, as the separate entry, without message or value (section 6.7, DR-22; N6, N7, N11);
- that interrupts and exit requests propagate (section 6.7; N8);
- one report entry per pair, the same alone and together for strategies without mutable state outside the engine (section 6.7 "Report", the engine's part of DR-22; N11);
- the snapshot refusals and that an empty execution gives an empty report (U5, U7, U8; N5);
- module-qualified type names, read without strategy code apart from the hash-collision limitation below, with the fallback of U9 (U2, U9; N9);
- each pair's context with its instrument's very snapshot, shared and never copied (section 6.7 "Snapshot"; N10).

These remain convention or review only:

- **Purity of a strategy**, and therefore DR-22 for strategies that share mutable state behind the engine's back (a module-level variable, or an attribute of a strategy object paired with several instruments, for example). The engine isolates what it holds (5.3 step 7); it does not and cannot isolate state a strategy keeps itself. N11 shows independence only for the test strategies, which keep no such state, and the engine cannot detect such sharing. As in SE-4, code under `sentaris_engine.strategies` is checked statically by SE-1.
- **The exception object is dropped**, but the strategy may have stored it or its message elsewhere. The report carries neither (N6); nothing else is in the engine's control.
- **A strategy that changes a shared snapshot** cannot: the snapshot is immutable (SE-3). Reaching its private attributes is out of scope, as in SE-3 section 9.
- **Reading `identity`** runs strategy code (a property). It is read once, before any evaluation (N4); a strategy that does more in it than return its identity is review only.
- **Execution itself reads no clock, payload, parameter value or state, and keeps nothing between calls** (DR-08, DR-23, section 6.5, DR-25). The SE-1 purity checks cover the clock and I/O; the rest is review (review F10).
- **The `try` wraps only the `evaluate_stateless` call** (5.3 step 7). N6 to N8 show what is caught; that no engine code sits inside the `try` is review.
- **A hash collision in a class dict.** `type`'s `__module__` descriptor is an ordinary lookup in the class's own dict. A class body or a metaclass `__prepare__` that plants a key whose hash collides with that of `"__module__"` makes the lookup call that key's `__eq__`, which is strategy code. The engine cannot prevent this without reading the dict itself; it is accepted as a contrived limitation of the guarantee in 5.5, with no defensive mechanism (re-review R2). In that case the planted `__eq__` runs, and if it raises, the exception leaves `execute` and no report is returned. N9 does not cover this case.
- **Finalizers.** A strategy-defined `__del__` on a dropped exception, a returned non-outcome or a strategy object runs strategy code at a point the engine does not control. Nothing the engine reports depends on it; it is not prevented.

## 10. Exclusions

- Building snapshots, and what the pairs of an instrument report when its snapshot cannot be built (SE-7b, SE-10, OD-3).
- Malformed parameters as a per-pair evaluation failure (SE-5b, OD-3).
- Stateful pairs: loading, passing and persisting state (SE-14, OD-17 to OD-20).
- Input declaration and the union of an instrument's needs (SE-7a, OD-13).
- Scheduling, choosing `as_of`, persistence and delivery of the report (OD-5, OD-11).
- Any real strategy (SE-12).
- No change to `docs/domain.md` beyond section 13, and none at all without the user's approval. No change to `docs/roadmap.md`.

## 11. Open questions

None blocks SE-5. Recorded, not decided here:

1. **Surrogates in a type name.** A class's `__qualname__` can hold lone surrogates, which SE-3 forbids in failure codes (SE-3 U3). Reporting the name as read applies section 6.7 as written; whether a reported name must later be encodable belongs to delivery (OD-11).

## 12. Decisions by the user (2026-11-13)

- **U1.** Execution catches exactly `Exception` and its subclasses. Every other `BaseException` (`KeyboardInterrupt`, `SystemExit`, `GeneratorExit`, a strategy-defined one) propagates. Answers SE-4 spec section 11, question 3.
- **U2.** A reported type name is module-qualified (`module.qualname`), for raised exceptions and non-outcomes alike. Answers SE-4 spec section 11, question 4.
- **U3.** A stateful strategy, or an object that follows neither contract, refuses the whole execution before anything runs, until SE-14 admits stateful pairs.
- **U4.** The fault entry distinguishes a raise from a non-outcome return.
- **U5.** A missing snapshot for a pair's instrument, a surplus snapshot for an instrument without a pair, and a snapshot whose `as_of` differs from the execution's each refuse the whole execution before anything runs. What the pairs of an instrument report when its snapshot cannot be built stays OD-3 (SE-10).
- **U6.** A pair accepts only an already built `Parameters`; anything else is refused when the pair is constructed. SE-5b adds the per-pair failure of section 6.5 for malformed raw parameters.

- **U7.** In answer to the specification review: an execution of an empty list of pairs is valid and gives a report with no entries. A lasting rule of section 6.7.
- **U8.** In answer to the specification review: one snapshot object given for two instrument keys refuses the whole execution before anything runs (section 6.7: "pairs of different instruments share nothing"). Part of U5.
- **U9.** In answer to the specification review: a type that records no usable module is named by its qualname alone; no module is invented. If that qualname is empty, the name is empty.

U3, U5, U6 and U8 are properties of SE-5's interface (prebuilt snapshots, stateless only, built parameters), which later slices change. They are not recorded in the domain document. U1, U2, U4, U7 and U9 are lasting rules of section 6.7 and are recorded there (section 13).

## 13. Proposed document changes (need the user's approval)

Each edit replaces the quoted "before" text by the "after" text in `docs/domain.md`; nothing else in the document changes. They alter no established rule (section 4) and add U1, U2, U4, U7 and U9 to section 6.7, whose heading already reads "amended 2026-11-13". `docs/roadmap.md` needs no change. The edits are made in the first task of the SE-5 plan. If the user does not approve them, none is made.

1. Section 6.7, "Unit of work" bullet. Before: `The same strategy may be paired with several instruments.` After:
   ```text
   The same strategy may be paired with several instruments. The list may be empty; the report then has no entries.
   ```
2. Section 6.7, "A strategy that raises" bullet. Before: `Only ordinary exceptions are caught; an interrupt or exit request propagates.` After:
   ```text
   Only ordinary exceptions are caught, that is, instances of the language's ordinary exception class (in Python, `Exception`); every other exception, an interrupt or exit request included, propagates. A type name is prefixed by the name of the module the type records, when it records the name of one as a non-empty string, so two types of the same name in different modules are told apart; no module name is invented. The entry states whether the strategy raised or returned a value that is not one of the three outcomes.
   ```

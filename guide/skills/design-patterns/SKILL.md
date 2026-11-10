---
name: design-patterns
description: "Applies the Observer, Strategy, Builder, Adapter, Singleton, Factory and Facade design patterns only when they add real value. Use it when designing, writing or refactoring code to decide whether a pattern solves a concrete problem or introduces unnecessary complexity."
---

# Design Patterns (Observer, Strategy, Builder, Adapter, Singleton, Factory, Facade)

## Core philosophy

A design pattern solves a concrete, recurring problem of coupling, creation
or behavior; it is not decoration. Apply one only when the problem exists
today (or there is a concrete, planned change) and when the simple
alternative is clearly worse. If the pattern doesn't remove coupling,
duplication or maintenance complexity, it is added complexity.

Consistency with the existing code weighs more than a pattern. If the
codebase already uses a convention to solve the problem, follow it even if
another pattern would be theoretically "better". Don't introduce a second way
of doing the same thing.

## Patterns

Each pattern, with when to apply it and when to ignore it:

- **Observer:** notifies multiple decoupled parties when something changes,
  without the emitter knowing the receivers. Apply when there are several
  real consumers of the same event or state change and direct coupling makes
  extending or testing harder. Ignore when there is a single consumer or a
  direct method call is enough.
- **Strategy:** swaps variants of an algorithm at runtime. Apply when there
  are several real variants of the same behavior and the choice depends on
  context or configuration. Ignore when there is a single variant or a simple
  conditional covers the case.
- **Builder:** builds complex objects step by step, separating construction
  from representation. Apply when the object has many optional parameters,
  construction has several steps, or you need several representations of the
  same object. Ignore when construction is simple or a constructor with
  parameters is enough.
- **Adapter:** makes incompatible interfaces compatible by wrapping one of
  them. Apply when integrating third-party libraries, legacy code or APIs
  whose contract you can't change, so they fit the interface your code
  expects. Ignore when you can change the interface directly.
- **Singleton:** guarantees a single instance with global access. Apply only
  when the resource is genuinely unique and shared (a connection, a cache),
  and even then prefer dependency injection so it can be tested. Ignore it in
  most cases: coupled global state is debt.
- **Factory:** centralizes object creation and can return different types
  depending on context. Apply when creation is complex, changes at runtime,
  or must stay in one place for several related types. Ignore when a simple,
  direct `new` is enough.
- **Facade:** offers a simple interface over a complex subsystem to reduce
  coupling. Apply when a client interacts with many internal pieces of a
  subsystem or library and the complexity makes it hard to use. Ignore when
  the subsystem is simple or clients need fine-grained control of its parts.

## Decision checklist before applying a pattern

Answer all four questions. If any fails, use the direct solution:

1. Does it solve a real problem that exists today (not a speculative one)?
2. Is the simple alternative (direct call, `new`, conditional) clearly worse?
3. Does it reduce coupling or complexity, or does it only add indirection?
4. Will anyone maintaining the code understand and sustain it easily?

## Warning signs

**Pattern by dogma:** Factory and Singleton for every class, Observer where a
direct method is enough, Builder for trivial objects, Strategy with a single
variant, Facade over code that is already simple. If the pattern is the only
thing justifying its own existence, don't apply it.

**Real problem without a pattern:** direct coupling that prevents testing or
extending, creation logic duplicated in several places, a client interacting
with too many internal pieces of a subsystem, several consumers of the same
change hooked up in a fragile way.

When in doubt, prefer the simplest direct solution that meets the
requirement, and adopt the pattern when the concrete problem proves it is
needed.

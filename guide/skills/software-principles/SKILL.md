---
name: software-principles
description: "Applies design principles (SOLID, KISS, DRY, YAGNI) pragmatically. Use it when writing, reviewing or refactoring code to decide when and how to abstract without falling into over-engineering."
---

# Software Principles (SOLID, KISS, DRY, YAGNI)

## Core philosophy

Design principles are decision tools, not dogmas. Apply them only when they
add real value: readability, maintainability, testability or a planned
change. Before applying any of them, ask what concrete problem it solves. If
the answer is "because it's the right thing" and nothing more, don't apply
it.

Consistency with the existing code weighs more than a principle. A pattern
already established in the codebase stays even if another one would be
technically "better". Don't introduce a second way of doing the same thing.

## SOLID

Each letter, with when to apply it and when to ignore it:

- **SRP (Single Responsibility):** a class or method does one thing and does
  it well. Apply when a change in one requirement forces you to touch several
  parts of the same object for different reasons. Ignore fragmentation for
  aesthetics or because "it looked nice": too many small classes are debt
  too.
- **OCP (Open/Closed):** extensible without modifying what exists. Apply when
  real, foreseeable variants appear that change the behavior. Ignore
  abstractions over code nobody has asked to extend.
- **LSP (Liskov Substitution):** a subclass must be able to replace its base
  without breaking the contract. Apply when you extend through inheritance.
  If the subclass violates or weakens the base's contract, use composition or
  rethink the design instead of forcing inheritance.
- **ISP (Interface Segregation):** don't force a consumer of an interface to
  depend on methods it doesn't use. Apply when there are consumers with
  different needs. Ignore the proliferation of tiny interfaces that only make
  navigation harder.
- **DIP (Dependency Inversion):** depend on abstractions, not on concretions.
  Inject dependencies and keep high-level parts unaware of low-level details.
  Apply when there is coupling that makes testing or changing hard. Ignore
  when the dependency is stable and simple.

## KISS

The simplest solution that works. Complexity is only justified when the
problem demands it, never in advance. Given two designs that meet the
requirement, choose the one with fewer moving parts. If a more complex
solution doesn't solve a real, measurable problem, it is over-engineering.

## DRY

Don't repeat logic that changes for the same reason. Extraction follows the
rule of three: extract on the third real use, not before. Before extracting,
check that the uses share the same intent and the same reason to change;
copying with variations usually means the concept isn't clear yet. A cheap,
honest duplication is worth more than a misguided premature abstraction.

## YAGNI

Don't build speculative features, abstractions or configurability. Generic
code is only justified by two or more real uses, not by "it might be
needed". Deferring a decision is cheap; reverting a premature abstraction is
expensive. Code that wasn't written doesn't have to be maintained.

## Decision checklist before abstracting

Before extracting a class, interface, helper or package, answer all four
questions. If any fails, don't abstract:

1. Does it have at least two real uses today (not anticipated ones)?
2. Does it simplify reading, or does it only add indirection?
3. Is there a concrete, planned change that justifies it?
4. Does the cost of keeping the duplication exceed the cost of the
   abstraction?

## Warning signs

**Over-engineering:** abstraction layers without consumers, interfaces with a
single implementer, configurability for cases that don't exist, inheritance
to "reuse" code, patterns applied because they are "the right ones".

**Under-engineering:** copy/pasted logic that changes for the same reason,
methods with several responsibilities, coupling to details that prevents
testing or changing, duplicated logic that has already caused diverging
bugs.

When in doubt between the two extremes, prefer the simplest code that covers
the current requirements and leaves room to evolve when a real reason
appears.

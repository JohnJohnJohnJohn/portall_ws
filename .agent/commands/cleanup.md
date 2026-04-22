Perform a single pass of code cleanup on the existing codebase. Your objective is to reduce complexity and line count while preserving all current behavior.

Constraints (hard rules):
- Do not add new features, new files, new abstractions, new dependencies, or new error-handling layers unless fixing a concrete, reproducible bug.
- Net lines of code must decrease or stay equal. Report the line-count delta at the end.
- Only touch a file if the change meets one of: removes dead/duplicate code, fixes a real bug with a reproducible trigger, improves readability without changing structure, or consolidates obvious duplication.
- No speculative refactors, no "future-proofing," no renaming for taste.

Process:
1. First, produce a short plan: list the specific files/functions you intend to change and the concrete reason for each. Stop and show me this plan before editing.
2. After I approve, make the minimal edits. Run tests/lints as the only definition of "done."
3. If tests pass and lints are clean, stop. Do not start another round. Do not search for more issues.

Output: a diff summary, the line-count delta, and a list of any issues you noticed but deliberately did not fix (so I can triage them).

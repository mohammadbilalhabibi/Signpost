# Manual review of run2-full

Same method as `run1-full-review.md` (LLM-graded, 19 November 2026): every answer read against its
rubric, key facts checked in the source text copies. Changes since run 1: publisher/scope/period
context line in chunk headers; prompt rules for conditions/reasons/contacts and for general vs
specific rules.

**Result: 31 pass, 8 partial, 1 fail (run 1: 28 / 10 / 2). Unsupported claims: 1 (Q34).**

Changed grades vs run 1:

| ID | Run 1 | Run 2 | Why |
|---|---|---|---|
| Q09 | partial | pass | D04 now retrieved: next-semester certificate available at semester start |
| Q13 | pass | partial | D04 no longer in the top 5: says the union-fee amount is not in the passages, does not ask which semester |
| Q23 | partial | pass | Adds the caretaker and the rental-bond voucher |
| Q27 | fail | pass | All four residences listed with addresses (D08, D14, D17) |
| Q38 | partial | pass | Asks which type of work (clarify) |

Still partial: Q04 (insurer's role), Q08 (terminal), Q16 (service-fee note), Q24 (previous
tenant's right), Q29 (D30/city form not retrieved), Q35 (bank fees), Q40 (threshold refusal,
no portal pointer).

Still failing: **Q34** again says "the three-month period refers to registering your address"
(the passage says register with the foreigners authority). Fix after this run: prompt rule 6
(keep each passage's wording for office/deadline; address registration and residence permit are
different procedures). Rerun of Q34 three times after the fix: all three correct (both rules
with their scope, apply before the visa expires, contact the foreigners authority).

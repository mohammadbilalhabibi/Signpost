# Manual review of run3-full (final run)

Same method as the earlier reviews (LLM-graded, 19 November 2026). Change since run 2: prompt rule 6
(keep each passage's wording for office/deadline; address registration and residence permit are
different procedures).

**Result: 31 pass, 9 partial, 0 fail.** One minor misattributed phrase (Q34, see below); no
other unsupported claims found.

Automatic metrics (`run3-full.md`): expected source in top 5 for 38/38 questions, all expected
sources for 33/38; an expected source cited in 38/38; mean citation precision 0.91; response
types: answer 36, clarify 1, not_found 1, refused 1, smalltalk 1.

| Grade | Questions |
|---|---|
| pass | Q01 Q02 Q03 Q05 Q06 Q07 Q09 Q10 Q11 Q12 Q14 Q15 Q17 Q18 Q19 Q20 Q21 Q22 Q23 Q25 Q26 Q27 Q28 Q30 Q31 Q32 Q33 Q35 Q36 Q37 Q39 |
| partial | Q04 Q08 Q13 Q16 Q24 Q29 Q34 Q38 Q40 |
| fail | – |

Partial, why:
- Q04: does not say that the insurer sends the confirmation.
- Q08: terminal not mentioned.
- Q13: D04 not in the top 5, so no union-fee amounts and no "which semester?" question.
- Q16: no note that service fees may apply depending on status.
- Q24: previous tenant's right to the room not mentioned.
- Q29: D30 (city page with the official form link) not retrieved; answers not_found while
  explaining the supplier-confirmation rule from D29.
- Q34: correct rule (apply before the visa expires; contact the foreigners authority; D19's
  three-month statement presented as a general overview), but says "the January 2026 overview
  says not to wait until three months", which D20 does not literally say.
- Q38: correct limits, but this run did not ask about residence conditions or job type (run 2 did:
  the LLM is not deterministic).
- Q40: refused by the score threshold (best 0.0004); the generic text says there is no live room
  data, but does not name the housing portal.

Fixed compared with run 1: Q09, Q14 (now adds that the union fee still applies), Q23, Q27
(was fail), Q34 (was fail), Q35.

# Manual review of run4-full

Changes since run 3: the user prompt states the student's question before and after the
passages, which are wrapped in `<passages>` tags (a passage ending like an FAQ heading,
"Questions regarding the application: ...", made the model answer "I don't see a question"
for "How do I apply for a room in a student residence?"); a reply of type answer/clarify
without any citation is sent once more with a correction (no retry was needed in this run).

Automatic metrics (`run4-full.md`): expected source in top 5 for 38/38, all expected sources
33/38, an expected source cited 38/38, mean citation precision 0.89, response types: answer 37,
clarify 1, refused 1, smalltalk 1, retries 0.

**Scope of this review (LLM-graded, 20 November 2026):** the 8 answers whose response type or cited
sources changed since run 3 (Q08, Q12, Q14, Q18, Q19, Q28, Q29, Q38) and the 9 answers graded
partial in run 3 (Q04, Q08, Q13, Q16, Q24, Q29, Q34, Q38, Q40) — 14 questions in total. The
other 26 answers kept their response type and cited sources and were **not** re-read, so no
full 40-question grade is claimed for this run.

| ID | Run 3 | Run 4 | Note |
|---|---|---|---|
| Q04 | partial | pass | Now explains that the public insurer sends the electronic confirmation |
| Q08 | partial | partial | Adds "re-register first, then validate" (D04); terminal still not mentioned |
| Q12 | pass | pass | DIT IT contact, ECRI contact not mixed in (answer instead of clarify) |
| Q13 | partial | partial | €60 / €500 and union fee; no amounts for the union fee, no "which semester?" |
| Q14 | pass | pass | EU/EEA exempt from the service fee; no claim about the union fee |
| Q16 | partial | partial | €87 for summer 2027; no note on status-dependent service fees |
| Q18 | pass | pass | Contact the Centre for Studies clerk; adds the summer-2027 period |
| Q19 | pass | pass | Apply before admission; no contractual obligation |
| Q24 | partial | partial | First-working-day rule and caretaker; previous tenant's right not mentioned |
| Q28 | pass | pass | International Office route; on-site contact from D17 (verified) |
| Q29 | partial | partial | Lists the confirmation contents from D29 §19(3) (verified); "No." is an inference; D30/city form link not retrieved |
| Q34 | partial | pass | Apply before the visa expires; three-month overview does not override it; contact the foreigners authority (misattribution gone) |
| Q38 | partial | pass | Limits and exceptions, then asks about the type of work |
| Q40 | partial | partial | Threshold refusal with the generic "no live data" text |

Result for the 14 reviewed questions: 8 pass, 6 partial, 0 fail (run 3 for the same 14:
5 pass, 9 partial). The housing question that triggered the fix was asked three times with the
real LLM after the change: three cited answers (D11, D12), no retry needed.

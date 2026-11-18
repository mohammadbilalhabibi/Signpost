# Manual review of run1-full

Reviewer: LLM-graded (not a human), 19 November 2026. Each answer in `run1-full.jsonl` was read
against its `expected_behavior` rubric, and its key facts were checked against the source text
copies in `DIT_Arrival_RAG_English/DIT_Arrival_RAG_English/text/`.

Grades: **pass** = rubric met and every claim supported by a cited passage; **partial** = claims
supported but a rubric point is missing; **fail** = wrong, incomplete in a way that misleads, or
an unsupported claim.

**Result: 28 pass, 10 partial, 2 fail. Unsupported claims: 1 (Q34).**

| ID | Grade | Note |
|---|---|---|
| Q01 | pass | Primuss login, photo, confirmation, documents, payment, deadline in letter |
| Q02 | pass | Full list with "if applicable" items; letter controls the list |
| Q03 | pass | Deadline varies; no invented date |
| Q04 | partial | Confirmation required; does not say the insurer transmits it |
| Q05 | pass | Public insurer + EHIC copy → digital confirmation |
| Q06 | pass | Posted to German address about a week before semester start |
| Q07 | pass | Collect at Centre for Studies from semester start |
| Q08 | partial | Validate each semester; terminal not mentioned; D04 not used |
| Q09 | partial | Primuss certificate path correct; D04 not retrieved, so no "next-semester certificate only at semester start" |
| Q10 | pass | Check-in link + matriculation number, password rules |
| Q11 | pass | Different numbers; matriculation number on admission registration certificate |
| Q12 | pass | it-support@th-deg.de + location, cited from D02 (same contact as D06); ECRI contact not mixed in |
| Q13 | pass | €60 / €500 / union fee per semester; asks which semester (clarify) |
| Q14 | pass | EU/EEA not subject to the service fee; no claim about the union fee |
| Q15 | pass | 8 Jan – 5 Feb 2027, semester named |
| Q16 | partial | €87 for summer 2027; no note that service fees may apply by status |
| Q17 | pass | €92 from winter 2027/28 |
| Q18 | pass | Contact the responsible Centre for Studies clerk; no promise |
| Q19 | pass | Apply before admission; no contractual obligation |
| Q20 | pass | Any time |
| Q21 | pass | Reminder on the 20th, confirm within 7 days |
| Q22 | pass | Only housing staff can change it; contact them |
| Q23 | partial | No weekend/holiday handover; caretaker not mentioned |
| Q24 | partial | First-working-day rule; previous tenant's right to the room not mentioned |
| Q25 | pass | Detterstraße 21, 94469 Deggendorf |
| Q26 | pass | Own kitchen and bathroom; no vacancy claim |
| Q27 | **fail** | Lists only the two Finkenhof residences; D14–D17 not retrieved |
| Q28 | pass | Exchange students apply via the International Office |
| Q29 | partial | Explains supplier confirmation requirement but answers not_found; D30 and city form link not retrieved |
| Q30 | pass | Two weeks from moving in; translated-summary label |
| Q31 | pass | Registration authority vs foreigners authority, separate processes |
| Q32 | pass | Full local checklist incl. enrolment + study-time certificates; QR note |
| Q33 | pass | QR code from the German checklist; labelled translation |
| Q34 | **fail** | Correct "before the visa expires", but claims the three-month period refers to address registration (unsupported; D19 says the foreigners authority within three months) and does not point to the local authority |
| Q35 | partial | Documents listed; no note that fees depend on the bank/account |
| Q36 | pass | One resident registers; paying resident's contribution number |
| Q37 | pass | Student status alone is no exemption; BAföG rule |
| Q38 | partial | 140/280 days or 20 h/week, auxiliary jobs, self-employment; does not ask about residence conditions or job type |
| Q39 | pass | Warm greeting, asks what is needed, no retrieval |
| Q40 | partial | Refused by the score threshold (best 0.0004); generic text says there is no live room data, but no pointer to the housing provider portal |

Fixes made after this review: publisher/scope/period context line in every chunk header
(retrieval for Q27-type questions), and prompt rules to keep conditions, reasons and contacts and
to present general vs specific rules with their scope instead of reinterpreting them (Q34).

# Evaluation run retrieval-hybrid

- Questions: 40 from `evaluation_questions.json`; mode `hybrid` (retrieval only)
- Settings: top_k_final=5, rerank_candidates=20, rerank_max_length=256, refusal_threshold=0.02, chunk_tokens=350, llm=gpt-6-luna
- Retrieval: expected source in top 5: 37/38; all expected sources: 34/38

| ID | Expected | Retrieved (top-k docs) | Cited | Type | Hit | Best score |
|---|---|---|---|---|---|---|
| Q01 | D01 | D01, D27, D03, D02 | - | - | True | 0.033 |
| Q02 | D01 | D03, D01, D27, D11 | - | - | True | 0.031 |
| Q03 | D01 | D01, D03, D11, D05 | - | - | True | 0.032 |
| Q04 | D28 | D28, D01, D24, D02, D07 | - | - | True | 0.033 |
| Q05 | D28 | D28, D07, D01, D03 | - | - | True | 0.033 |
| Q06 | D02 | D02, D27, D03, D01, D06 | - | - | True | 0.033 |
| Q07 | D02 | D28, D02, D06, D01, D27 | - | - | True | 0.032 |
| Q08 | D02, D04 | D02, D04, D05, D21 | - | - | True | 0.033 |
| Q09 | D06, D04 | D04, D05, D06, D02 | - | - | True | 0.032 |
| Q10 | D06 | D02, D19, D06, D20 | - | - | True | 0.033 |
| Q11 | D06 | D06, D29, D07, D11 | - | - | True | 0.033 |
| Q12 | D06 | D02, D06, D07 | - | - | True | 0.033 |
| Q13 | D03, D04 | D03, D04, D01 | - | - | True | 0.032 |
| Q14 | D03 | D03, D04, D25 | - | - | True | 0.032 |
| Q15 | D05 | D05, D04, D02 | - | - | True | 0.033 |
| Q16 | D04, D05 | D05, D04, D03, D02 | - | - | True | 0.033 |
| Q17 | D04 | D04, D05, D03, D02 | - | - | True | 0.033 |
| Q18 | D04 | D04, D02, D05 | - | - | True | 0.033 |
| Q19 | D12 | D12, D11, D08 | - | - | True | 0.033 |
| Q20 | D11 | D11, D12, D01 | - | - | True | 0.032 |
| Q21 | D11 | D11, D12 | - | - | True | 0.033 |
| Q22 | D11 | D11, D12 | - | - | True | 0.033 |
| Q23 | D13, D12 | D12, D13, D25, D11 | - | - | True | 0.033 |
| Q24 | D12, D13 | D13, D19, D29, D02, D12 | - | - | True | 0.032 |
| Q25 | D15 | D15, D16, D08 | - | - | True | 0.033 |
| Q26 | D17 | D17, D15, D16 | - | - | True | 0.032 |
| Q27 | D14, D15, D16, D17 | D11, D12, D08 | - | - | False | 0.030 |
| Q28 | D08 | D08, D17, D11 | - | - | True | 0.033 |
| Q29 | D29, D30 | D12, D29, D13 | - | - | True | 0.032 |
| Q30 | D30, D29 | D08, D29, D30 | - | - | True | 0.031 |
| Q31 | D30, D27 | D19, D29, D27 | - | - | True | 0.032 |
| Q32 | D27 | D27, D11, D14 | - | - | True | 0.032 |
| Q33 | D27 | D27, D19, D20, D07 | - | - | True | 0.033 |
| Q34 | D20, D27 | D19, D21, D20 | - | - | True | 0.032 |
| Q35 | D22 | D22, D19, D02, D06 | - | - | True | 0.033 |
| Q36 | D25 | D25, D04, D16 | - | - | True | 0.033 |
| Q37 | D25 | D25, D03 | - | - | True | 0.032 |
| Q38 | D23 | D23, D21, D03 | - | - | True | 0.033 |
| Q39 | - | D29, D02, D13, D10 | - | - | None | 0.029 |
| Q40 | - | D08, D13, D14 | - | - | None | 0.033 |

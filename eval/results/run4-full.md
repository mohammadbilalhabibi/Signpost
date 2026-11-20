# Evaluation run run4-full

- Questions: 40 from `evaluation_questions.json`; mode `hybrid_rerank`
- Settings: top_k_final=5, rerank_candidates=20, rerank_max_length=256, refusal_threshold=0.02, chunk_tokens=350, llm=gpt-6-luna
- Retrieval: expected source in top 5: 38/38; all expected sources: 33/38
- Citations: cites an expected source: 38/38; mean citation precision: 0.89
- Response types: answer 37, clarify 1, refused 1, smalltalk 1
- Median time per question: 11.1 s

| ID | Expected | Retrieved (top-k docs) | Cited | Type | Hit | Best score |
|---|---|---|---|---|---|---|
| Q01 | D01 | D01, D28, D03, D27 | D01, D28 | answer | True | 0.994 |
| Q02 | D01 | D01, D28, D27, D11 | D01, D28 | answer | True | 0.960 |
| Q03 | D01 | D01, D03, D11 | D01 | answer | True | 0.747 |
| Q04 | D28 | D28, D01, D11, D03 | D28 | answer | True | 0.996 |
| Q05 | D28 | D28, D01, D07, D27, D24 | D28 | answer | True | 0.922 |
| Q06 | D02 | D02, D06, D28, D01 | D02 | answer | True | 0.892 |
| Q07 | D02 | D02, D06, D28, D27, D01 | D02 | answer | True | 0.599 |
| Q08 | D02, D04 | D02, D04, D11, D05 | D02, D04 | answer | True | 0.184 |
| Q09 | D06, D04 | D06, D04, D05, D11, D01 | D06, D04 | answer | True | 0.668 |
| Q10 | D06 | D02, D06, D07 | D06 | answer | True | 0.315 |
| Q11 | D06 | D06, D07, D29 | D06 | answer | True | 0.942 |
| Q12 | D06 | D02, D06, D07 | D02, D06 | answer | True | 0.942 |
| Q13 | D03, D04 | D03, D01, D28 | D03 | answer | True | 0.228 |
| Q14 | D03 | D01, D03, D04, D25 | D03, D04 | answer | True | 0.718 |
| Q15 | D05 | D05, D04, D02 | D05 | answer | True | 1.000 |
| Q16 | D04, D05 | D04, D05, D03 | D04, D05 | answer | True | 0.984 |
| Q17 | D04 | D04, D05, D03 | D04 | answer | True | 0.934 |
| Q18 | D04 | D04, D02, D05 | D04, D05 | answer | True | 0.943 |
| Q19 | D12 | D12, D11, D08 | D12 | answer | True | 0.996 |
| Q20 | D11 | D11, D01, D02 | D11 | answer | True | 0.030 |
| Q21 | D11 | D11, D12, D08 | D11 | answer | True | 0.942 |
| Q22 | D11 | D11, D08, D12 | D11 | answer | True | 0.992 |
| Q23 | D13, D12 | D12, D13, D25, D29 | D12, D13 | answer | True | 0.662 |
| Q24 | D12, D13 | D13, D12, D11 | D13, D12 | answer | True | 0.338 |
| Q25 | D15 | D15, D08, D16 | D15 | answer | True | 0.962 |
| Q26 | D17 | D17, D08, D16 | D17 | answer | True | 0.972 |
| Q27 | D14, D15, D16, D17 | D08, D11, D14, D17 | D08, D14, D17 | answer | True | 0.994 |
| Q28 | D08 | D08, D17 | D08, D17 | answer | True | 0.992 |
| Q29 | D29, D30 | D29, D12, D13 | D29 | answer | True | 0.031 |
| Q30 | D30, D29 | D30, D29, D08, D19 | D30 | answer | True | 0.997 |
| Q31 | D30, D27 | D20, D27, D29 | D20, D27 | answer | True | 0.101 |
| Q32 | D27 | D27, D11 | D27 | answer | True | 0.997 |
| Q33 | D27 | D27, D07, D29 | D27 | answer | True | 0.984 |
| Q34 | D20, D27 | D19, D20, D21 | D19, D20 | answer | True | 0.607 |
| Q35 | D22 | D22, D19, D21, D06 | D22 | answer | True | 0.993 |
| Q36 | D25 | D25, D08, D04 | D25 | answer | True | 0.494 |
| Q37 | D25 | D25, D04, D03 | D25 | answer | True | 0.988 |
| Q38 | D23 | D23, D19, D21 | D23 | clarify | True | 0.907 |
| Q39 | - | - | - | smalltalk | None | - |
| Q40 | - | D08, D13, D14 | - | refused | None | 0.001 |

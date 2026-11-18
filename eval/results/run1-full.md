# Evaluation run run1-full

- Questions: 40 from `evaluation_questions.json`; mode `hybrid_rerank`
- Settings: top_k_final=5, rerank_candidates=20, rerank_max_length=256, refusal_threshold=0.02, chunk_tokens=350, llm=gpt-6-luna
- Retrieval: expected source in top 5: 37/38; all expected sources: 33/38
- Citations: cites an expected source: 36/38; mean citation precision: 0.88
- Response types: answer 36, clarify 1, not_found 1, refused 1, smalltalk 1
- Median time per question: 11.8 s

| ID | Expected | Retrieved (top-k docs) | Cited | Type | Hit | Best score |
|---|---|---|---|---|---|---|
| Q01 | D01 | D01, D28, D27, D02 | D01, D28 | answer | True | 0.995 |
| Q02 | D01 | D01, D28, D27, D11 | D01, D28 | answer | True | 0.970 |
| Q03 | D01 | D01, D03, D04 | D01 | answer | True | 0.788 |
| Q04 | D28 | D28, D01, D11, D07 | D28 | answer | True | 0.997 |
| Q05 | D28 | D28, D01, D27, D07, D24 | D28 | answer | True | 0.917 |
| Q06 | D02 | D02, D28, D06, D01, D27 | D02 | answer | True | 0.911 |
| Q07 | D02 | D02, D06, D28, D27 | D02 | answer | True | 0.561 |
| Q08 | D02, D04 | D02, D04, D11 | D02 | answer | True | 0.298 |
| Q09 | D06, D04 | D06, D05, D11, D01, D27 | D06 | answer | True | 0.681 |
| Q10 | D06 | D02, D06, D07 | D06 | answer | True | 0.393 |
| Q11 | D06 | D06, D07, D29 | D06 | answer | True | 0.949 |
| Q12 | D06 | D02, D06, D07 | D02 | answer | True | 0.941 |
| Q13 | D03, D04 | D03, D04, D01 | D04, D03 | clarify | True | 0.268 |
| Q14 | D03 | D04, D03, D01 | D03 | answer | True | 0.791 |
| Q15 | D05 | D05, D04, D02, D03 | D05 | answer | True | 1.000 |
| Q16 | D04, D05 | D04, D05, D03 | D04, D05 | answer | True | 0.992 |
| Q17 | D04 | D04, D05, D02, D03 | D04 | answer | True | 0.968 |
| Q18 | D04 | D02, D04, D05, D29 | D04 | answer | True | 0.118 |
| Q19 | D12 | D12, D11, D08 | D12, D08 | answer | True | 0.965 |
| Q20 | D11 | D11, D01 | D11 | answer | True | 0.127 |
| Q21 | D11 | D11, D12 | D11 | answer | True | 0.934 |
| Q22 | D11 | D11, D08 | D11 | answer | True | 0.990 |
| Q23 | D13, D12 | D12, D13, D25, D29, D11 | D12 | answer | True | 0.781 |
| Q24 | D12, D13 | D13, D12, D11 | D12 | answer | True | 0.426 |
| Q25 | D15 | D15, D08, D17, D16 | D15 | answer | True | 0.996 |
| Q26 | D17 | D17, D08, D16 | D17, D08 | answer | True | 0.993 |
| Q27 | D14, D15, D16, D17 | D08, D11 | D08 | answer | False | 0.979 |
| Q28 | D08 | D08, D17 | D08 | answer | True | 0.994 |
| Q29 | D29, D30 | D29, D12, D13 | D29 | not_found | True | 0.061 |
| Q30 | D30, D29 | D30, D08, D29, D19 | D30 | answer | True | 0.997 |
| Q31 | D30, D27 | D20, D29, D27 | D20, D27, D29 | answer | True | 0.133 |
| Q32 | D27 | D27, D08, D20, D14 | D27 | answer | True | 0.583 |
| Q33 | D27 | D27, D07, D29 | D27 | answer | True | 0.982 |
| Q34 | D20, D27 | D19, D20, D21 | D20 | answer | True | 0.669 |
| Q35 | D22 | D22, D19, D21 | D22 | answer | True | 0.994 |
| Q36 | D25 | D25, D08, D04 | D25 | answer | True | 0.716 |
| Q37 | D25 | D25, D03, D04 | D25 | answer | True | 0.981 |
| Q38 | D23 | D23, D19, D21 | D23 | answer | True | 0.949 |
| Q39 | - | - | - | smalltalk | None | - |
| Q40 | - | D08, D13, D14 | - | refused | None | 0.000 |

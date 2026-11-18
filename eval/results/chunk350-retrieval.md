# Evaluation run chunk350-retrieval

- Questions: 40 from `evaluation_questions.json`; mode `hybrid_rerank` (retrieval only)
- Settings: top_k_final=5, rerank_candidates=20, rerank_max_length=256, refusal_threshold=0.1, chunk_tokens=350, llm=gpt-6-luna
- Retrieval: expected source in top 5: 37/38; all expected sources: 33/38

| ID | Expected | Retrieved (top-k docs) | Cited | Type | Hit | Best score |
|---|---|---|---|---|---|---|
| Q01 | D01 | D01, D28, D27, D02 | - | - | True | 0.995 |
| Q02 | D01 | D01, D28, D27, D11 | - | - | True | 0.970 |
| Q03 | D01 | D01, D03, D04 | - | - | True | 0.788 |
| Q04 | D28 | D28, D01, D11, D07 | - | - | True | 0.997 |
| Q05 | D28 | D28, D01, D27, D07, D24 | - | - | True | 0.917 |
| Q06 | D02 | D02, D28, D06, D01, D27 | - | - | True | 0.910 |
| Q07 | D02 | D02, D06, D28, D27 | - | - | True | 0.561 |
| Q08 | D02, D04 | D02, D04, D11 | - | - | True | 0.298 |
| Q09 | D06, D04 | D06, D05, D11, D01, D27 | - | - | True | 0.681 |
| Q10 | D06 | D02, D06 | - | - | True | 0.393 |
| Q11 | D06 | D06, D07 | - | - | True | 0.949 |
| Q12 | D06 | D02, D06, D07 | - | - | True | 0.941 |
| Q13 | D03, D04 | D03, D04, D01 | - | - | True | 0.268 |
| Q14 | D03 | D04, D03, D01 | - | - | True | 0.791 |
| Q15 | D05 | D05, D04, D02, D03 | - | - | True | 1.000 |
| Q16 | D04, D05 | D04, D05, D03 | - | - | True | 0.992 |
| Q17 | D04 | D04, D05, D02, D03 | - | - | True | 0.968 |
| Q18 | D04 | D02, D04, D05, D29 | - | - | True | 0.118 |
| Q19 | D12 | D12, D11, D08 | - | - | True | 0.965 |
| Q20 | D11 | D11, D01 | - | - | True | 0.127 |
| Q21 | D11 | D11 | - | - | True | 0.934 |
| Q22 | D11 | D11 | - | - | True | 0.990 |
| Q23 | D13, D12 | D12, D13, D25, D29, D11 | - | - | True | 0.781 |
| Q24 | D12, D13 | D13, D12, D11 | - | - | True | 0.426 |
| Q25 | D15 | D15, D08, D17, D16 | - | - | True | 0.996 |
| Q26 | D17 | D17, D08, D16 | - | - | True | 0.993 |
| Q27 | D14, D15, D16, D17 | D08 | - | - | False | 0.979 |
| Q28 | D08 | D08, D17 | - | - | True | 0.994 |
| Q29 | D29, D30 | D29, D12 | - | - | True | 0.061 |
| Q30 | D30, D29 | D30, D08, D29, D19 | - | - | True | 0.997 |
| Q31 | D30, D27 | D20, D29, D27 | - | - | True | 0.133 |
| Q32 | D27 | D27, D08, D20, D14 | - | - | True | 0.584 |
| Q33 | D27 | D27, D07, D29 | - | - | True | 0.982 |
| Q34 | D20, D27 | D19, D20, D21 | - | - | True | 0.669 |
| Q35 | D22 | D22, D19, D21 | - | - | True | 0.994 |
| Q36 | D25 | D25 | - | - | True | 0.716 |
| Q37 | D25 | D25 | - | - | True | 0.981 |
| Q38 | D23 | D23, D19, D21 | - | - | True | 0.949 |
| Q39 | - | D07, D02, D29, D10 | - | - | None | 0.046 |
| Q40 | - | D08, D13 | - | - | None | 0.000 |

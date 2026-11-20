# Evaluation run retrieval-bm25

- Questions: 40 from `evaluation_questions.json`; mode `bm25` (retrieval only)
- Settings: top_k_final=5, rerank_candidates=20, rerank_max_length=256, refusal_threshold=0.02, chunk_tokens=350, llm=gpt-6-luna
- Retrieval: expected source in top 5: 35/38; all expected sources: 29/38

| ID | Expected | Retrieved (top-k docs) | Cited | Type | Hit | Best score |
|---|---|---|---|---|---|---|
| Q01 | D01 | D01, D19, D27, D03 | - | - | True | 17.944 |
| Q02 | D01 | D11, D19, D22, D03, D25 | - | - | False | 8.336 |
| Q03 | D01 | D11, D03, D05, D01 | - | - | True | 9.089 |
| Q04 | D28 | D28, D20, D11, D24, D19 | - | - | True | 18.350 |
| Q05 | D28 | D28, D24, D19, D21, D08 | - | - | True | 10.960 |
| Q06 | D02 | D02, D27, D03 | - | - | True | 16.924 |
| Q07 | D02 | D02, D28, D08 | - | - | True | 11.792 |
| Q08 | D02, D04 | D04, D02, D05, D19, D21 | - | - | True | 11.693 |
| Q09 | D06, D04 | D11, D27, D05, D04 | - | - | True | 7.933 |
| Q10 | D06 | D02, D07, D27, D22 | - | - | False | 5.410 |
| Q11 | D06 | D06, D07, D11 | - | - | True | 13.768 |
| Q12 | D06 | D02, D06, D07, D25 | - | - | True | 10.254 |
| Q13 | D03, D04 | D03, D04, D01 | - | - | True | 13.323 |
| Q14 | D03 | D04, D03, D25 | - | - | True | 13.679 |
| Q15 | D05 | D05, D04, D02 | - | - | True | 22.183 |
| Q16 | D04, D05 | D05, D04, D02 | - | - | True | 18.937 |
| Q17 | D04 | D04, D02, D05, D03 | - | - | True | 16.157 |
| Q18 | D04 | D04, D02, D05 | - | - | True | 18.609 |
| Q19 | D12 | D11, D12, D08 | - | - | True | 7.764 |
| Q20 | D11 | D01, D09, D19, D11 | - | - | True | 5.257 |
| Q21 | D11 | D11, D12 | - | - | True | 16.411 |
| Q22 | D11 | D11, D12 | - | - | True | 6.813 |
| Q23 | D13, D12 | D13, D12, D09, D08 | - | - | True | 9.041 |
| Q24 | D12, D13 | D02, D30, D13, D29, D19 | - | - | True | 7.348 |
| Q25 | D15 | D15, D16, D08 | - | - | True | 10.930 |
| Q26 | D17 | D17, D15, D16 | - | - | True | 14.573 |
| Q27 | D14, D15, D16, D17 | D11, D12, D08 | - | - | False | 10.108 |
| Q28 | D08 | D17, D08 | - | - | True | 12.972 |
| Q29 | D29, D30 | D12, D13, D08, D29, D11 | - | - | True | 7.879 |
| Q30 | D30, D29 | D29, D08 | - | - | True | 8.082 |
| Q31 | D30, D27 | D29, D30, D20, D19 | - | - | True | 9.624 |
| Q32 | D27 | D20, D27, D10, D22 | - | - | True | 9.356 |
| Q33 | D27 | D27, D07, D19, D01, D25 | - | - | True | 12.718 |
| Q34 | D20, D27 | D19, D21, D20 | - | - | True | 15.475 |
| Q35 | D22 | D22, D19, D02, D21 | - | - | True | 15.249 |
| Q36 | D25 | D25, D08, D15 | - | - | True | 14.080 |
| Q37 | D25 | D25, D03, D02 | - | - | True | 11.530 |
| Q38 | D23 | D23, D21 | - | - | True | 14.801 |
| Q39 | - | D02, D19, D07, D29, D20 | - | - | None | 3.934 |
| Q40 | - | D08, D13, D14 | - | - | None | 4.992 |

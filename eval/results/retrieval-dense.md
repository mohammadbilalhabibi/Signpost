# Evaluation run retrieval-dense

- Questions: 40 from `evaluation_questions.json`; mode `dense` (retrieval only)
- Settings: top_k_final=5, rerank_candidates=20, rerank_max_length=256, refusal_threshold=0.02, chunk_tokens=350, llm=gpt-6-luna
- Retrieval: expected source in top 5: 38/38; all expected sources: 34/38

| ID | Expected | Retrieved (top-k docs) | Cited | Type | Hit | Best score |
|---|---|---|---|---|---|---|
| Q01 | D01 | D01, D27, D02, D07 | - | - | True | 0.888 |
| Q02 | D01 | D01, D27, D28, D03 | - | - | True | 0.846 |
| Q03 | D01 | D01, D28, D03, D27 | - | - | True | 0.854 |
| Q04 | D28 | D28, D01, D27, D03 | - | - | True | 0.894 |
| Q05 | D28 | D28, D27, D01, D02, D07 | - | - | True | 0.866 |
| Q06 | D02 | D27, D02, D01, D06, D28 | - | - | True | 0.886 |
| Q07 | D02 | D27, D28, D06, D01, D02 | - | - | True | 0.865 |
| Q08 | D02, D04 | D02, D04, D23, D25 | - | - | True | 0.843 |
| Q09 | D06, D04 | D04, D01, D05, D06 | - | - | True | 0.833 |
| Q10 | D06 | D02, D19, D06, D04 | - | - | True | 0.850 |
| Q11 | D06 | D29, D06, D11 | - | - | True | 0.825 |
| Q12 | D06 | D02, D06, D07, D28 | - | - | True | 0.836 |
| Q13 | D03, D04 | D03, D04, D28 | - | - | True | 0.880 |
| Q14 | D03 | D03, D04, D25 | - | - | True | 0.855 |
| Q15 | D05 | D05, D04 | - | - | True | 0.877 |
| Q16 | D04, D05 | D05, D04, D25, D03 | - | - | True | 0.833 |
| Q17 | D04 | D05, D04, D25 | - | - | True | 0.817 |
| Q18 | D04 | D04, D02, D19, D29 | - | - | True | 0.842 |
| Q19 | D12 | D12, D11 | - | - | True | 0.892 |
| Q20 | D11 | D11, D12 | - | - | True | 0.837 |
| Q21 | D11 | D11, D12 | - | - | True | 0.862 |
| Q22 | D11 | D11, D12 | - | - | True | 0.882 |
| Q23 | D13, D12 | D12, D13, D29 | - | - | True | 0.851 |
| Q24 | D12, D13 | D12, D13, D11 | - | - | True | 0.856 |
| Q25 | D15 | D15, D16, D08 | - | - | True | 0.899 |
| Q26 | D17 | D17, D08, D16 | - | - | True | 0.852 |
| Q27 | D14, D15, D16, D17 | D08, D14, D17 | - | - | True | 0.882 |
| Q28 | D08 | D08, D17, D11 | - | - | True | 0.863 |
| Q29 | D29, D30 | D29, D12 | - | - | True | 0.845 |
| Q30 | D30, D29 | D30, D02, D08, D29, D05 | - | - | True | 0.892 |
| Q31 | D30, D27 | D19, D27, D29 | - | - | True | 0.836 |
| Q32 | D27 | D27, D11, D12, D14 | - | - | True | 0.875 |
| Q33 | D27 | D27, D29 | - | - | True | 0.869 |
| Q34 | D20, D27 | D21, D19, D20 | - | - | True | 0.864 |
| Q35 | D22 | D22, D19, D02, D29 | - | - | True | 0.876 |
| Q36 | D25 | D25, D14, D16 | - | - | True | 0.876 |
| Q37 | D25 | D25, D03 | - | - | True | 0.886 |
| Q38 | D23 | D23, D03 | - | - | True | 0.865 |
| Q39 | - | D10, D24, D02 | - | - | None | 0.780 |
| Q40 | - | D08, D12, D17 | - | - | None | 0.786 |

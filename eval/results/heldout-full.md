# Evaluation run heldout-full

- Questions: 25 from `heldout_questions.json`; mode `hybrid_rerank`
- Settings: top_k_final=5, rerank_candidates=20, rerank_max_length=256, refusal_threshold=0.02, chunk_tokens=350, llm=gpt-6-luna
- Retrieval: expected source in top 5: 20/20; all expected sources: 19/20
- Citations: cites an expected source: 20/20; mean citation precision: 0.91
- Response types: answer 20, clarify 1, not_found 2, refused 2
- Median time per question: 11.7 s

| ID | Expected | Retrieved (top-k docs) | Cited | Type | Hit | Best score |
|---|---|---|---|---|---|---|
| H01 | D09 | D09, D08, D02 | D09 | answer | True | 0.999 |
| H02 | D18 | D07, D18, D02, D03 | D18 | answer | True | 0.367 |
| H03 | D25 | D25, D08, D13 | D25 | answer | True | 0.981 |
| H04 | D24 | D24, D07 | D24 | answer | True | 0.967 |
| H05 | D24 | D24, D27, D29 | D24 | answer | True | 0.943 |
| H06 | D24 | D24, D28, D19, D21 | D24, D28 | answer | True | 0.039 |
| H07 | D21 | D21, D20, D27 | D21, D20 | answer | True | 0.926 |
| H08 | D21 | D21, D19, D11 | D21 | answer | True | 0.991 |
| H09 | D21 | D21, D23, D25 | D21 | answer | True | 0.996 |
| H10 | D06 | D06, D08, D07 | D06 | answer | True | 0.037 |
| H11 | D06 | D06, D05, D20, D11 | D06 | answer | True | 0.091 |
| H12 | D06 | D07, D27, D06 | D06 | answer | True | 0.036 |
| H13 | D14 | D14, D15, D17, D16 | D14 | answer | True | 0.993 |
| H14 | D10 | D10, D02, D01, D27, D28 | D10 | answer | True | 0.788 |
| H15 | D07 | D07, D01, D06 | D07 | answer | True | 0.080 |
| H16 | D22, D30 | D22, D19, D21, D06 | D22, D06 | answer | True | 0.993 |
| H17 | D26, D10 | D02, D26, D27, D10, D03 | D26, D27, D10 | answer | True | 0.727 |
| H18 | D14, D16 | D08, D16, D14 | D16, D14 | answer | True | 0.789 |
| H19 | D23, D21 | D23, D21, D27, D25, D20 | D23 | clarify | True | 0.800 |
| H20 | D08, D25 | D08, D25 | D08, D25 | answer | True | 0.948 |
| H21 | - | D08, D02, D14, D09 | - | refused | None | 0.002 |
| H22 | - | D05, D02, D09, D15, D08 | - | not_found | None | 0.023 |
| H23 | - | D11, D06, D01, D21, D02 | - | not_found | None | 0.030 |
| H24 | - | D20, D21, D27 | D20 | answer | None | 0.034 |
| H25 | - | D07, D02, D23, D19 | - | refused | None | 0.005 |

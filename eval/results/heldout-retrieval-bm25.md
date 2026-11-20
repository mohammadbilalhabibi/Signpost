# Evaluation run heldout-retrieval-bm25

- Questions: 25 from `heldout_questions.json`; mode `bm25` (retrieval only)
- Settings: top_k_final=5, rerank_candidates=20, rerank_max_length=256, refusal_threshold=0.02, chunk_tokens=350, llm=gpt-6-luna
- Retrieval: expected source in top 5: 15/20; all expected sources: 14/20

| ID | Expected | Retrieved (top-k docs) | Cited | Type | Hit | Best score |
|---|---|---|---|---|---|---|
| H01 | D09 | D09, D08, D02, D17 | - | - | True | 18.865 |
| H02 | D18 | D18, D03, D04 | - | - | True | 12.383 |
| H03 | D25 | D25, D07, D14 | - | - | True | 27.026 |
| H04 | D24 | D24, D02, D09 | - | - | True | 9.446 |
| H05 | D24 | D24, D19, D12, D21 | - | - | True | 22.419 |
| H06 | D24 | D24, D28, D19, D20 | - | - | True | 31.039 |
| H07 | D21 | D21, D20, D27, D19 | - | - | True | 10.573 |
| H08 | D21 | D21, D20 | - | - | True | 11.832 |
| H09 | D21 | D21, D23, D19 | - | - | True | 10.345 |
| H10 | D06 | D08, D02 | - | - | False | 5.533 |
| H11 | D06 | D11, D27, D01, D20, D21 | - | - | False | 4.564 |
| H12 | D06 | D08, D27, D30, D07 | - | - | False | 6.538 |
| H13 | D14 | D14, D08, D12 | - | - | True | 6.980 |
| H14 | D10 | D10, D03, D01, D04, D20 | - | - | True | 14.813 |
| H15 | D07 | D27, D01, D14, D15, D16 | - | - | False | 8.291 |
| H16 | D22, D30 | D22, D19, D21, D27 | - | - | True | 23.278 |
| H17 | D26, D10 | D02, D07, D24 | - | - | False | 8.721 |
| H18 | D14, D16 | D16, D15, D14 | - | - | True | 16.054 |
| H19 | D23, D21 | D23, D25, D02, D19, D21 | - | - | True | 19.194 |
| H20 | D08, D25 | D08, D25 | - | - | True | 24.478 |
| H21 | - | D02, D08, D07 | - | - | None | 8.251 |
| H22 | - | D09, D08, D30 | - | - | None | 2.291 |
| H23 | - | D09, D21, D12, D11 | - | - | None | 4.710 |
| H24 | - | D20, D24, D19, D21 | - | - | None | 13.853 |
| H25 | - | D19, D22, D21, D24 | - | - | None | 7.037 |

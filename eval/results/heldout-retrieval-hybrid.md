# Evaluation run heldout-retrieval-hybrid

- Questions: 25 from `heldout_questions.json`; mode `hybrid` (retrieval only)
- Settings: top_k_final=5, rerank_candidates=20, rerank_max_length=256, refusal_threshold=0.02, chunk_tokens=350, llm=gpt-6-luna
- Retrieval: expected source in top 5: 20/20; all expected sources: 19/20

| ID | Expected | Retrieved (top-k docs) | Cited | Type | Hit | Best score |
|---|---|---|---|---|---|---|
| H01 | D09 | D09, D02, D08 | - | - | True | 0.033 |
| H02 | D18 | D03, D04, D18 | - | - | True | 0.032 |
| H03 | D25 | D25, D07, D14 | - | - | True | 0.033 |
| H04 | D24 | D24, D08, D02 | - | - | True | 0.033 |
| H05 | D24 | D24, D19, D12 | - | - | True | 0.033 |
| H06 | D24 | D24, D19, D28, D03 | - | - | True | 0.033 |
| H07 | D21 | D21, D20, D19 | - | - | True | 0.033 |
| H08 | D21 | D21, D20 | - | - | True | 0.033 |
| H09 | D21 | D21, D19, D23 | - | - | True | 0.033 |
| H10 | D06 | D02, D06 | - | - | True | 0.029 |
| H11 | D06 | D06, D04, D11, D01, D27 | - | - | True | 0.031 |
| H12 | D06 | D27, D07, D06, D02 | - | - | True | 0.032 |
| H13 | D14 | D14, D08 | - | - | True | 0.032 |
| H14 | D10 | D01, D10, D03, D28, D27 | - | - | True | 0.032 |
| H15 | D07 | D01, D27, D07, D06, D14 | - | - | True | 0.032 |
| H16 | D22, D30 | D22, D19, D27 | - | - | True | 0.033 |
| H17 | D26, D10 | D02, D27, D26, D10, D08 | - | - | True | 0.033 |
| H18 | D14, D16 | D16, D15, D14 | - | - | True | 0.033 |
| H19 | D23, D21 | D23, D21, D27, D19 | - | - | True | 0.033 |
| H20 | D08, D25 | D08, D25, D11 | - | - | True | 0.033 |
| H21 | - | D02, D14, D08 | - | - | None | 0.032 |
| H22 | - | D09, D30, D08, D14 | - | - | None | 0.029 |
| H23 | - | D21, D11 | - | - | None | 0.031 |
| H24 | - | D20, D24, D27 | - | - | None | 0.033 |
| H25 | - | D19, D23, D24, D02 | - | - | None | 0.033 |

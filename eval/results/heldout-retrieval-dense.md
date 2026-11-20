# Evaluation run heldout-retrieval-dense

- Questions: 25 from `heldout_questions.json`; mode `dense` (retrieval only)
- Settings: top_k_final=5, rerank_candidates=20, rerank_max_length=256, refusal_threshold=0.02, chunk_tokens=350, llm=gpt-6-luna
- Retrieval: expected source in top 5: 17/20; all expected sources: 15/20

| ID | Expected | Retrieved (top-k docs) | Cited | Type | Hit | Best score |
|---|---|---|---|---|---|---|
| H01 | D09 | D09, D02 | - | - | True | 0.892 |
| H02 | D18 | D01, D03, D04, D28 | - | - | False | 0.865 |
| H03 | D25 | D25, D13, D03 | - | - | True | 0.892 |
| H04 | D24 | D24, D02, D07 | - | - | True | 0.828 |
| H05 | D24 | D24, D25, D27 | - | - | True | 0.853 |
| H06 | D24 | D24, D03, D19 | - | - | True | 0.861 |
| H07 | D21 | D21, D20, D19 | - | - | True | 0.865 |
| H08 | D21 | D21, D11, D19 | - | - | True | 0.888 |
| H09 | D21 | D21, D19, D03 | - | - | True | 0.868 |
| H10 | D06 | D06, D02 | - | - | True | 0.832 |
| H11 | D06 | D06, D02, D05, D04 | - | - | True | 0.841 |
| H12 | D06 | D27, D07, D28, D01 | - | - | False | 0.857 |
| H13 | D14 | D14, D17, D16 | - | - | True | 0.901 |
| H14 | D10 | D27, D01, D02, D28, D03 | - | - | False | 0.838 |
| H15 | D07 | D07, D01, D06 | - | - | True | 0.829 |
| H16 | D22, D30 | D22, D19, D29 | - | - | True | 0.900 |
| H17 | D26, D10 | D02, D26, D27, D10, D03 | - | - | True | 0.863 |
| H18 | D14, D16 | D16, D08, D15 | - | - | True | 0.825 |
| H19 | D23, D21 | D23, D21, D27 | - | - | True | 0.872 |
| H20 | D08, D25 | D08, D25, D11 | - | - | True | 0.878 |
| H21 | - | D14, D02, D08, D17 | - | - | None | 0.779 |
| H22 | - | D14, D15, D09, D08, D17 | - | - | None | 0.847 |
| H23 | - | D06, D11, D02 | - | - | None | 0.825 |
| H24 | - | D20, D29 | - | - | None | 0.829 |
| H25 | - | D19, D23, D02 | - | - | None | 0.771 |

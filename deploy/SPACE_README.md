---
title: Signpost
emoji: 🧭
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Cited answers for international students arriving at DIT
---

# Signpost

AI-powered assistant for international students arriving at Deggendorf Institute of
Technology (DIT) and settling in Deggendorf: enrolment, fees, student ID and IT accounts,
student housing, address registration, residence permits, health insurance, banking and
student jobs. Answers are in English, and every answer links to the original official page.
If the sources do not answer a question, Signpost says so.

- Hybrid retrieval (BM25 + multilingual-e5 with Reciprocal Rank Fusion), an int8 ONNX
  reranker (bge-reranker-v2-m3) and an OpenAI-compatible LLM.
- Knowledge base: 30 English public sources (DIT, Studierendenwerk Niederbayern/Oberpfalz,
  City and District of Deggendorf, Make it in Germany, DAAD, Beitragsservice, the English
  translation of the Federal Registration Act), captured on 18 November 2026. The original
  publishers keep all rights; check the linked pages before relying on fees, deadlines or
  contacts.
- Not an official DIT service. No live data (free rooms, appointments, application status).
- Answers take about 20 seconds on the CPU basic hardware.

Source code, evaluation and documentation: https://github.com/mohammadbilalhabibi/Signpost

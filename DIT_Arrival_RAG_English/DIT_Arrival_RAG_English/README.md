# DIT International Student Arrival Assistant

Compiled on 18 November 2026. Focused on international degree students settling in Deggendorf. Documents retain explicitly labelled exchange-student or other-campus passages where relevant.

## Contents

- documents/ contains 30 sources selected for ingestion as PDFs.
- text/ contains one English text copy for each of those 30 sources, with source metadata. These copies simplify extraction from webpages and multi-column originals.
- reference_only/ contains the original February 2025 housing flyer. Its embedded fonts drop letters during extraction. Use the four residence webpages in documents/ for retrieval.
- sources.json and sources.csv map every PDF to its exact original URL, publisher, language, topic, scope, capture date, edition or semester, review note and SHA-256 checksum.
- source_review.json explains the older, inconsistent or out-of-scope material omitted from ingestion and identifies replacement sources.
- evaluation_questions.json contains 40 questions and expected-source/answer rubrics for the future chatbot. No chatbot has been run or scored as part of this collection.

## Using it in a project

1. Unzip this folder into your chatbot project.
2. Keep each source's metadata with its chunks. Index the text copy OR its matching PDF once.
3. Test the chatbot before publishing answers to users. Check correctness, source citations, campus/student-type/semester filtering and appropriate handling of missing evidence.

## Source formats and important distinctions

The pack contains 31 source PDFs in total. Five are unchanged publisher PDFs, including the reference-only housing flyer. The remaining 26 are readable PDF exports of selected official webpage content, including two documents containing labelled English translations or translated summaries (D27 and D30). Their source headers identify the transformation. Web navigation, scripts, unrelated page sections, image-only material and interactive tools are omitted.

Text copies of multi-page publisher PDFs preserve source page numbers. D20's single-page, five-step infographic was reordered into its visible reading sequence. Native originals remain unchanged. Website captures preserve the selected text and links where extracted. All URLs remain in sources.json even when the source PDF itself does not print its URL.

D27 combines the authority's own English document list with a labelled translation of its German QR-photo and submission instructions. D30 is an English summary of the city's German registration page. Cite the original public-authority pages. Actual forms and booking pages may be in German.

## Dates and source precedence

The capture date records when a source was retrieved. It does not mean the publisher updated it on that date. Unknown publication dates remain null. Refresh fees, deadlines, visa rules, contact assignments and transport information before relying on them for a new semester or future date.

D05 concerns summer semester 2027 and was posted on 1 October 2026. D04 states semester-specific student-union contributions. These figures must stay attached to their periods. D03 gives service-fee exemptions. D29 is the officially hosted English registration-law translation incorporating amendments through 23 October 2024; the current German law and local authority should be checked where legal interpretation or later amendments matter.

Use D01 for DIT's online enrolment process, because the national overview D19 describes universities more generally. For visa holders, D20 requires applying for the residence permit before the visa expires. Use D14-D17 for provider-specific residence information. D08 preserves the university's exchange-student application guidance. D30 gives the service-specific Bürgeramt telephone; D26 is a broader English directory.

## Coverage limits

This collection supports the agreed arrival and settling-in scope. It does not establish live room vacancies, appointment slots, individual visa or insurance decisions, personal application status, or future prices beyond the periods stated in the sources. A current DIT academic-calendar section contained mismatched examination years and was omitted pending confirmation. Detailed degree examination regulations and admission eligibility are outside this arrival collection.

Some current public webpages themselves contain broad or imperfect statements. The review notes record identified conflicts; this is not a certification of every factual sentence. Accurate answers require retrieving the relevant source passages and evaluating the chatbot's output.

## Public sources and attribution

The source documents were accessible without login. Original publishers retain their rights. This pack is a study and development source collection assembled from their public material. Retain attribution and original URLs when building the chatbot.

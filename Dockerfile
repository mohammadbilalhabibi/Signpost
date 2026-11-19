# Signpost on Hugging Face Spaces (Docker SDK) or any Docker host.
#
# Build:  docker build -t signpost .
# Run:    docker run --rm -p 7860:7860 --env-file .env signpost
#
# At build time this downloads the int8 ONNX reranker and the e5 embedding model, ingests
# the English source collection and builds the BM25/FAISS index, so the container starts
# without network access to the Hub and the first request is fast. Secrets (LLM_API_KEY)
# come only from environment variables at run time.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Non-root user with UID 1000 (the Hugging Face Spaces convention).
RUN useradd --create-home --uid 1000 user
WORKDIR /home/user/app

# 1) Dependencies (cached until pyproject.toml changes). CPU-only PyTorch first, so pip
#    does not pull the much larger CUDA build; then the project's runtime dependencies.
#    constraints.txt pins the versions that were tested.
COPY --chown=user pyproject.toml constraints.txt ./
RUN pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu \
 && python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" > /tmp/requirements.txt \
 && pip install -r /tmp/requirements.txt -c constraints.txt \
 && rm /tmp/requirements.txt

USER user
ENV HOME=/home/user \
    HF_HOME=/home/user/app/.cache/huggingface \
    PYTHONPATH=/home/user/app

# 2) Models (cached until the repo/revision changes): the int8 ONNX reranker from its
#    Hugging Face model repo (made by scripts/export_reranker.py) and the e5 embedding model.
ARG RERANKER_REPO=MohammadBilalHabibi12345/signpost-reranker-onnx-int8
ARG RERANKER_REVISION=main
RUN hf download "$RERANKER_REPO" model.onnx export_info.json tokenizer.json tokenizer_config.json \
        --revision "$RERANKER_REVISION" --local-dir models/bge-reranker-v2-m3-onnx-int8 \
 && rm -rf models/bge-reranker-v2-m3-onnx-int8/.cache \
 && test -f models/bge-reranker-v2-m3-onnx-int8/model.onnx
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-base')"

# 3) Code and knowledge base (only the English text copies + sources.json, no PDFs).
COPY --chown=user app ./app
COPY --chown=user scripts ./scripts
COPY --chown=user DIT_Arrival_RAG_English/DIT_Arrival_RAG_English/sources.json DIT_Arrival_RAG_English/DIT_Arrival_RAG_English/sources.json
COPY --chown=user DIT_Arrival_RAG_English/DIT_Arrival_RAG_English/text DIT_Arrival_RAG_English/DIT_Arrival_RAG_English/text

# 4) Ingest the collection and build the index inside the image, so the index fingerprint
#    matches the chunks the app loads.
RUN mkdir -p data/processed index logs \
 && python scripts/ingest.py \
 && python scripts/build_index.py

# No Hub calls at run time: every model is already in the image.
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

EXPOSE 7860
CMD ["python", "-m", "uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "7860"]

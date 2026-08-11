FROM python:3.12-slim

# Non-root user (uid 1000) as recommended for Hugging Face Docker Spaces and
# good practice for Azure container hosts.
RUN useradd -m -u 1000 user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# trustbandits package for the live simulator (from the analysis repo).
RUN pip install --no-cache-dir git+https://github.com/dominikpegler/trust-bandits-analysis.git

USER user

COPY --chown=user . $HOME/app

# Bake the compact DuckDB dataset into the image (zero cold-start latency).
# Rebuild the image to refresh the data; the canonical artifact lives in Azure
# Blob Storage (see scripts/export_duckdb.py).
COPY --chown=user data/trust_bandits.duckdb $HOME/app/data/trust_bandits.duckdb

ENV DATA_BACKEND=duckdb \
    DUCKDB_PATH=$HOME/app/data/trust_bandits.duckdb

EXPOSE 7860
CMD ["streamlit", "run", "app.py", "--server.port=7860", "--server.address=0.0.0.0"]

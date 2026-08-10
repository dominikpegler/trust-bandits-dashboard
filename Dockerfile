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

EXPOSE 7860
CMD ["streamlit", "run", "app.py", "--server.port=7860", "--server.address=0.0.0.0"]

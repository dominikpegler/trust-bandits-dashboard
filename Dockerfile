FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Optional: trustbandits package for the live simulator. If you want the live
# simulator in the deployed Space, copy the package in and uncomment:
# COPY trustbandits/ /app/trustbandits/
# RUN pip install --no-cache-dir -e /app/trustbandits

COPY . .

EXPOSE 7860
CMD ["streamlit", "run", "app.py", "--server.port=7860", "--server.address=0.0.0.0"]

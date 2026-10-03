FROM python:3.12-slim
WORKDIR /app
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt
COPY researchpilot researchpilot
COPY frontend frontend
COPY examples examples
RUN useradd --create-home appuser && mkdir /app/data && chown -R appuser:appuser /app
USER appuser
ENV RP_MODE=offline RP_DATA_DIR=/app/data PYTHONUNBUFFERED=1
EXPOSE 8765
CMD ["python", "-m", "uvicorn", "researchpilot.app:app", "--host", "0.0.0.0", "--port", "8765"]

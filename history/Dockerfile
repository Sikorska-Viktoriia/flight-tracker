FROM python:3.12-slim
WORKDIR /app
COPY history/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --system --uid 10001 appuser
COPY history/__init__.py ./history/__init__.py
COPY history/app ./history/app
COPY database ./database
USER appuser
EXPOSE 8000
CMD ["uvicorn", "history.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

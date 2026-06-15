# chapter-03/catalog-service/Dockerfile
# chapter-03/search-service/Dockerfile
# chapter-03/payments-service/Dockerfile
# chapter-03/recommendations-service/Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

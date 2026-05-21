FROM python:3.12-slim

WORKDIR /app

# deps first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# source
COPY . .

# brief store mount point (Docker volume)
RUN mkdir -p /app/services/store

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
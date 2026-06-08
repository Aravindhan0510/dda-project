FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY gcp_client.py .
COPY upload_service.py .
ENV PORT=8080
EXPOSE 8080
CMD ["python", "upload_service.py"]

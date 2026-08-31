FROM python:3.11-slim
RUN pip install --no-cache-dir requests
WORKDIR /app
COPY health_check.py .
CMD ["python", "health_check.py"]

FROM python:3.11-slim
RUN pip install --no-cache-dir requests
WORKDIR /app
COPY refresh_superset.py .
CMD ["python", "refresh_superset.py"]

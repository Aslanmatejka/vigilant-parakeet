FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy application code
COPY backend/ ./backend/

# Railway sets PORT automatically
ENV PORT=8000
EXPOSE ${PORT}

CMD python -m backend.run_forever

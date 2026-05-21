FROM python:3.12-slim

WORKDIR /app

# Copy and install just enough to verify
COPY pyproject.toml .
RUN pip install --no-cache-dir . 2>&1 | tail -5

# Copy app code
COPY . .

EXPOSE 8001
ENV HOME=/root

# Simple test: import app and start
CMD python -c "
import sys, os
print('Python OK', flush=True)
print('CWD:', os.getcwd(), flush=True)
print('Files:', os.listdir('.'), flush=True)
import app.main
print('App imported OK', flush=True)
import uvicorn
print('Uvicorn imported OK', flush=True)
uvicorn.run('app.main:app', host='0.0.0.0', port=8001, log_level='debug')
"

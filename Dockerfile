# --- Stage 1: Build Frontend ---
FROM node:18-alpine as frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ .
RUN npm run build

# --- Stage 2: Python Backend ---
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .

# Copy built frontend from Stage 1
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

# The command to run your bot (Default to API)
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of your application code
COPY . .

# Expose the port for uvicorn
EXPOSE 8000

# Run the application with Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

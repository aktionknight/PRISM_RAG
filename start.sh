#!/bin/bash
# Start Ollama in the background
ollama serve &

# Wait for Ollama to be ready
echo "Waiting for Ollama to start..."
while ! curl -s http://127.0.0.1:11434/api/tags > /dev/null; do
    sleep 1
done
echo "Ollama is running."

# Start the FastAPI engine
echo "Starting PRISM Engine..."
exec uvicorn slrag.api.app:create_app --factory --host 0.0.0.0 --port 8000

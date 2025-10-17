FROM nvidia/cuda:12.4.0-base-ubuntu22.04

# Install Python and pip
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    vim \
    curl \
    wget \
    htop \
    procps \
    net-tools \
    dnsutils \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Create mxwhisper user
RUN useradd --create-home --shell /bin/bash mxwhisper

# Copy project files
COPY . /app

# Set ownership of /app to mxwhisper user
RUN chown -R mxwhisper:mxwhisper /app

WORKDIR /app

# Switch to mxwhisper user for Python operations
USER mxwhisper

# Install dependencies and application as mxwhisper user
RUN uv sync --no-dev
RUN uv pip install -e .

# Preload Whisper model during build (configurable via build arg)
ARG WHISPER_MODEL_SIZE=medium
RUN uv run python -c "import whisper; whisper.load_model('${WHISPER_MODEL_SIZE}')"

# Create uploads directory
RUN mkdir -p /app/uploads

# Expose port
EXPOSE 8000

# Run the app
CMD ["uv", "run", "mxwhisper", "--host", "0.0.0.0", "--port", "8000"]
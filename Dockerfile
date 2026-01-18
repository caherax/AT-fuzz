FROM aflplusplus/aflplusplus:latest

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies and build tools
RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    tar \
    cmake \
    autoconf \
    automake \
    libtool \
    pkg-config \
    file \
    bubblewrap \
    && rm -rf /var/lib/apt/lists/*

# Create Python virtual environment and install dependencies
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN /opt/venv/bin/pip install --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install matplotlib

# Set working directory
WORKDIR /fuzzer

# Copy source code
COPY src/ /fuzzer/src/
COPY README.md /fuzzer/
COPY docs/ /fuzzer/docs/

# Create output directory
RUN mkdir -p output

# Default command: start bash for interactive use
CMD ["/bin/bash"]
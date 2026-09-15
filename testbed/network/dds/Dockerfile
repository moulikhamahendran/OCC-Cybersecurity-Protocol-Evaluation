FROM python:3.13-slim-bookworm AS cyclonedds-build

ARG CYCLONEDDS_VERSION=11.0.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        git \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone \
        --branch "${CYCLONEDDS_VERSION}" \
        --depth 1 \
        https://github.com/eclipse-cyclonedds/cyclonedds.git \
        /tmp/cyclonedds \
    && cmake \
        -S /tmp/cyclonedds \
        -B /tmp/cyclonedds/build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/opt/cyclonedds \
        -DENABLE_SECURITY=ON \
        -DBUILD_EXAMPLES=OFF \
        -DBUILD_TESTING=OFF \
    && cmake --build /tmp/cyclonedds/build --parallel \
    && cmake --install /tmp/cyclonedds/build


FROM python:3.13-slim-bookworm

ARG CYCLONEDDS_VERSION=11.0.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        iproute2 \
        libssl3 \
        procps \
    && rm -rf /var/lib/apt/lists/*

COPY --from=cyclonedds-build \
    /opt/cyclonedds \
    /opt/cyclonedds

ENV CYCLONEDDS_HOME=/opt/cyclonedds
ENV LD_LIBRARY_PATH=/opt/cyclonedds/lib
ENV PATH=/opt/cyclonedds/bin:${PATH}
ENV PYTHONUNBUFFERED=1

RUN python -m pip install --no-cache-dir \
        "cyclonedds==${CYCLONEDDS_VERSION}" \
        "jsonschema==4.26.0" \
        "psutil==7.2.2"

WORKDIR /workspace

CMD ["bash"]

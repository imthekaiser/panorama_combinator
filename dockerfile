FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    coreutils \
    findutils \
    grep \
    sed \
    gawk \
    python3 \
    python3-numpy \
    python3-opencv \
    hugin-tools \
    enblend \
    enfuse \
    libimage-exiftool-perl \
    imagemagick \
    libvips-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY process_all.sh /app/process_all.sh
COPY check_pto_crop.py /app/check_pto_crop.py
COPY fill_sky.py /app/fill_sky.py

RUN chmod +x /app/process_all.sh /app/check_pto_crop.py /app/fill_sky.py

ENTRYPOINT ["/app/process_all.sh"]
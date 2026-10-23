FROM envoyproxy/envoy:v1.40.0
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*
COPY repro.py /repro.py
ENTRYPOINT ["python3", "/repro.py"]

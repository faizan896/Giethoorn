# Exact Rust toolchain and locked crate graph; build entirely inside Linux.
FROM rust:1.91.1-bookworm@sha256:c1e5f19e773b7878c3f7a805dd00a495e747acbdc76fb2337a4ebf0418896b33 AS builder
RUN apt-get update && apt-get install -y --no-install-recommends python3 pkg-config libssl-dev ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /build
ENV CARGO_BUILD_JOBS=2
COPY . .
RUN cargo build --release --locked \
    && cargo test --locked --all-targets \
    && python3 -m unittest discover -s ops -p 'test_*.py' \
    && bash -n scripts/mac ops/run-collector-service \
    && mkdir -p /export/usr/local/bin /export/app \
    && cp target/release/giethoorn /export/usr/local/bin/giethoorn \
    && cp -R ops web fixtures /export/app/ \
    && chmod -R a+rX /export

FROM debian:bookworm-slim@sha256:734a72b3d6142a71993b4bc580ca01d8ca687f77a2c422d96a961d3376b179bc AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends python3 libssl3 ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /export/ /
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 1000:1000
RUN python3 /app/ops/paper_demo.py --help > /dev/null && /usr/local/bin/giethoorn paper-replay --input /app/fixtures/paper-synthetic-v1.jsonl > /dev/null
CMD ["/usr/local/bin/giethoorn", "--help"]

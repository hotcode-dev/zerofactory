FROM oven/bun:1.1 as builder
WORKDIR /app

# Build dashboard
COPY dashboard /app/dashboard
RUN cd dashboard && bun install && bun run build

# Setup backend
COPY src /app/src
RUN cd src && bun install

FROM oven/bun:1.1 as runner
WORKDIR /app

# Copy built dashboard
COPY --from=builder /app/dashboard/dist ./dashboard/dist

# Copy backend
COPY --from=builder /app/src ./src

WORKDIR /app/src

EXPOSE 10000

ENV PORT=10000
CMD ["bun", "run", "index.ts"]

FROM node:20-alpine

WORKDIR /app

# The relay has zero runtime dependencies (only Node 20 stdlib + global fetch).
# package.json is shipped purely so `node --test` / tooling can resolve the
# package name; no `npm install` step is required or desirable.
COPY package.json ./
COPY src ./src

ENV NODE_ENV=production \
    PORT=8080 \
    WEBHOOK_PATH=/eas

EXPOSE 8080

USER node

CMD ["node", "src/server.js"]

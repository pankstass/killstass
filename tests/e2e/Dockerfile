# v1.9: browser e2e / accessibility test runner for scripts/e2e-docker.sh. Developer tooling only:
# the production images (api, db, proxy) contain no Node.js. Keep the tag equal to the playwright version
# in package.json, otherwise the bundled browser does not match.
ARG PLAYWRIGHT_IMAGE=mcr.microsoft.com/playwright:v1.64.1-noble
FROM ${PLAYWRIGHT_IMAGE}
WORKDIR /e2e
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund --ignore-scripts && npm cache clean --force
COPY web ./web
COPY tests/e2e ./tests/e2e
RUN mkdir -p test-results && chown pwuser test-results
USER pwuser
ENV E2E_BASE_URL=http://localhost:8000
CMD ["npm", "run", "e2e"]

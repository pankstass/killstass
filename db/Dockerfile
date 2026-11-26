ARG POSTGRES_IMAGE=postgres:16-alpine
FROM ${POSTGRES_IMAGE}
COPY migrations /opt/killstass/migrations
COPY legacy-seed.json /opt/killstass/seed.json
COPY seed.json /opt/killstass/catalog-current.json
COPY migrate.sh /opt/killstass/
COPY migrate.sh /docker-entrypoint-initdb.d/10-killstass.sh
RUN chmod +x /opt/killstass/migrate.sh /docker-entrypoint-initdb.d/10-killstass.sh

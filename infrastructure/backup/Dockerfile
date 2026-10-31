# Image for the nightly database backup (Render cron job `osiris-db-backup`, see render.yaml).
# pg_dump must match the server's major version: Supabase runs PostgreSQL 17.
FROM postgres:17-alpine

RUN apk add --no-cache aws-cli openssl

COPY backup.sh /usr/local/bin/osiris-backup
RUN chmod 0755 /usr/local/bin/osiris-backup

USER postgres
ENTRYPOINT ["/usr/local/bin/osiris-backup"]

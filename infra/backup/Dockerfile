# Syroce PMS - Offsite yedekleme konteyneri (mongodump + awscli)
# mongo:7 tabani mongodump/mongorestore araclarini icerir; uzerine
# AWS CLI eklenir. mongodump yoksa database-tools paketi kurulur.
FROM mongo:7

RUN apt-get update \
 && apt-get install -y --no-install-recommends awscli ca-certificates tzdata \
 && (command -v mongodump >/dev/null 2>&1 || apt-get install -y --no-install-recommends mongodb-database-tools) \
 && rm -rf /var/lib/apt/lists/*

COPY backup.sh /usr/local/bin/backup.sh
RUN chmod +x /usr/local/bin/backup.sh

ENTRYPOINT ["/usr/local/bin/backup.sh"]

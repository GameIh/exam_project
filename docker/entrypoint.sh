#!/bin/sh
set -e

python <<'PY'
import os
import time

import psycopg2

host = os.environ.get("POSTGRES_HOST", "postgres")
port = int(os.environ.get("POSTGRES_PORT", "5432"))
database = os.environ.get("POSTGRES_DB", "exam_db")
user = os.environ.get("POSTGRES_USER", "exam_user")
password = os.environ.get("POSTGRES_PASSWORD", "exam_pass")

for attempt in range(60):
    try:
        connection = psycopg2.connect(
            host=host,
            port=port,
            dbname=database,
            user=user,
            password=password,
        )
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA IF NOT EXISTS exam;")
        connection.close()
        break
    except psycopg2.OperationalError:
        if attempt == 59:
            raise
        time.sleep(1)
PY

python manage.py migrate --noinput

if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  python manage.py seed_demo_data
fi

exec "$@"

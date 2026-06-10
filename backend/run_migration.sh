#!/bin/bash
set -e

cd /home/sirobo/papergenerator/backend

export DATABASE_URL="postgresql://papergenerator:PaperGen2026!Secure@localhost:5432/papergenerator"

echo "=== Step 1: alembic heads ==="
.venv/bin/alembic heads

echo ""
echo "=== Step 2: alembic current ==="
.venv/bin/alembic current

echo ""
echo "=== Step 3: alembic upgrade head ==="
.venv/bin/alembic upgrade head

echo ""
echo "=== Step 4: alembic current (verification) ==="
.venv/bin/alembic current

echo ""
echo "=== Step 5: Verify 'mode' column in conversations ==="
echo "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'conversations' AND column_name = 'mode';" | .venv/bin/python -c "
import psycopg2
import os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
cur.execute(\"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'conversations' AND column_name = 'mode'\")
result = cur.fetchone()
if result:
    print(f'OK - mode column exists: {result}')
else:
    print('ERROR - mode column NOT found')
cur.close()
conn.close()
"


#!/usr/bin/bash
set -ex

# kolla_set_configs
echo "/usr/bin/supervisord -c /etc/dingoops/supervisord.conf" >/run_command

mapfile -t CMD < <(tail /run_command | xargs -n 1)
# kolla_extend_start
pip install -e .
# start celery worker
#celery -A dingoops.celery_api.workers worker --loglevel=info

alembic -c ./db/alembic/alembic.ini upgrade head

echo "Running command: ${CMD[*]}"
exec "${CMD[@]}"


#!/usr/bin/bash
set -ex

# kolla_set_configs
echo "/usr/bin/supervisord -c /etc/dingo-command/supervisord.conf" >/run_command

mapfile -t CMD < <(tail /run_command | xargs -n 1)
# kolla_extend_start
pip install -e .
# start celery worker
#celery -A dingo_command.celery_api.workers worker --loglevel=info

alembic -c ./dingo_command/db/alembic/alembic.ini upgrade head

echo "Running command: ${CMD[*]}"
exec "${CMD[@]}"

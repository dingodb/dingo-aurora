#!/usr/bin/bash
set -ex

# copy dir
TARGET_DIR="/var/lib/dingo-command/ansible-deploy"
if [ ! -d "$TARGET_DIR" ]; then
    echo "the target dir is not exist, copying dir"
    mkdir -p /var/lib/dingo-command
    cp -r /opt/dingo-aurora/dingo_command/templates/ansible-deploy /var/lib/dingo-command
else
    echo "the target dir is exist"
fi

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

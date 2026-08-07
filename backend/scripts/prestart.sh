#! /usr/bin/env bash

set -e
set -x

# DB đã sẵn sàng (depends_on: condition: service_healthy trong compose)
alembic upgrade head

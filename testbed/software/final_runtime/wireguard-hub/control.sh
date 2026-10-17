#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$DIR"

ACTION="${1:-}"

case "$ACTION" in

    start)
        sudo docker compose \
            --env-file .env \
            up -d
        ;;

    stop)
        sudo docker compose \
            --env-file .env \
            down
        ;;

    restart)
        sudo docker compose \
            --env-file .env \
            down

        sudo docker compose \
            --env-file .env \
            up -d
        ;;

    status)
        sudo docker compose ps
        ;;

    logs)
        sudo docker compose logs \
            --tail=200 \
            wg-easy
        ;;

    health)
        "$DIR/health.sh"
        ;;

    *)
        echo "Usage:"
        echo "  $0 start"
        echo "  $0 stop"
        echo "  $0 restart"
        echo "  $0 status"
        echo "  $0 logs"
        echo "  $0 health"
        exit 1
        ;;
esac

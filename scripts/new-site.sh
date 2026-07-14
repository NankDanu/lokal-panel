#!/usr/bin/env bash
# ============================================================
# Buat nginx site untuk project di folder development Windows
# (support subfolder)
#
# Usage (dari dalam WSL):
#   sudo bash new-site.sh -p <path> -v <versi-php> [-r subdir] [-d domain]
#
#   -p  Path project, relatif dari BASE_DIR (boleh subfolder),
#       atau path absolut (mis. /home/user/dev/app)
#   -v  Versi PHP (7.4 / 8.1 / 8.3 ...)
#   -r  Subdir document root, mis. "public" untuk Laravel (opsional)
#   -d  Custom domain lokal (opsional, default: <nama-folder>.lo)
#
# Contoh (BASE_DIR=/mnt/c/Dev):
#   sudo bash new-site.sh -p toko-online -v 8.3 -r public
#       -> http://toko-online.lo  (root: /mnt/c/Dev/toko-online/public)
#
#   sudo bash new-site.sh -p clients/kasir-app -v 7.4 -d kasir.lo
#       -> http://kasir.lo        (root: /mnt/c/Dev/clients/kasir-app)
# ============================================================
set -euo pipefail

# Base folder project di Windows (versi path WSL-nya).
# Sesuaikan, atau override saat menjalankan: SITE_BASE=/mnt/d/Web new-site.sh ...
BASE_DIR="${SITE_BASE:-/mnt/c/Dev}"
TLD="lo"             # TLD default domain lokal

PROJECT="" PHPV="" PUBDIR="" DOMAIN=""

while getopts "p:v:r:d:h" opt; do
  case $opt in
    p) PROJECT="$OPTARG" ;;
    v) PHPV="$OPTARG" ;;
    r) PUBDIR="$OPTARG" ;;
    d) DOMAIN="$OPTARG" ;;
    h|*) grep '^#' "$0" | head -25; exit 0 ;;
  esac
done

[ -n "$PROJECT" ] && [ -n "$PHPV" ] || {
  echo "Usage: new-site.sh -p <path-project> -v <versi-php> [-r subdir-public] [-d domain]"
  exit 1
}

# Path absolut atau relatif dari BASE_DIR (subfolder didukung: clients/app-a)
case "$PROJECT" in
  /*) BASE="$PROJECT" ;;
  *)  BASE="$BASE_DIR/$PROJECT" ;;
esac

ROOT="$BASE${PUBDIR:+/$PUBDIR}"
NAME="$(basename "$PROJECT")"
DOMAIN="${DOMAIN:-$NAME.$TLD}"
SOCK="/run/php/php$PHPV-fpm.sock"
CONF="/etc/nginx/sites-available/$DOMAIN.conf"

[ -d "$ROOT" ] || { echo "ERROR: folder $ROOT tidak ada. Buat dulu foldernya, atau cek BASE_DIR di script ini."; exit 1; }
[ -S "$SOCK" ] || { echo "ERROR: php$PHPV-fpm tidak jalan ($SOCK tidak ada)."; exit 1; }
[ -f "/etc/nginx/sites-enabled/$DOMAIN.conf" ] && echo "WARN: $DOMAIN sudah ada, akan ditimpa."

cat > "$CONF" <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    root $ROOT;
    index index.php index.html;

    access_log /var/log/nginx/$DOMAIN.access.log;
    error_log  /var/log/nginx/$DOMAIN.error.log;

    client_max_body_size 64M;

    location / {
        try_files \$uri \$uri/ /index.php?\$query_string;
    }

    location ~ \.php\$ {
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:$SOCK;
        fastcgi_read_timeout 300;
    }

    location ~ /\.(?!well-known) {
        deny all;
    }
}
EOF

ln -sf "$CONF" /etc/nginx/sites-enabled/$DOMAIN.conf
nginx -t && systemctl reload nginx

echo ""
echo "============================================================"
echo "Site dibuat : http://$DOMAIN"
echo "PHP         : $PHPV ($SOCK)"
echo "Root        : $ROOT"
echo ""
echo "LANGKAH TERAKHIR (di Windows, sekali per domain):"
echo "  Notepad as Administrator -> C:\\Windows\\System32\\drivers\\etc\\hosts"
echo ""
echo "  127.0.0.1  $DOMAIN"
echo "============================================================"

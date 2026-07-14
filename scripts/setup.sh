#!/usr/bin/env bash
# ============================================================
# Setup nginx + multi versi PHP-FPM di WSL (Ubuntu)
# Jalankan sekali dari dalam WSL, dari folder scripts project, contoh:
#   sudo bash /mnt/c/Dev/lokalan/panel/scripts/setup.sh
# ============================================================
set -euo pipefail

# Versi PHP yang diinstall — ubah sesuai kebutuhan
PHP_VERSIONS="7.4 8.1 8.3"

echo "==> Update & tambah PPA ondrej/php"
apt-get update
apt-get install -y software-properties-common curl
add-apt-repository -y ppa:ondrej/php
apt-get update

echo "==> Install nginx"
apt-get install -y nginx
systemctl enable --now nginx

for V in $PHP_VERSIONS; do
  echo "==> Install PHP $V (fpm + ekstensi umum)"
  apt-get install -y \
    php$V-fpm php$V-cli php$V-mysql php$V-pgsql php$V-sqlite3 \
    php$V-mbstring php$V-xml php$V-curl php$V-zip php$V-gd \
    php$V-intl php$V-bcmath php$V-opcache php$V-redis

  echo "==> Tuning opcache PHP $V (penting: /mnt/c lambat, opcache wajib)"
  cat > /etc/php/$V/fpm/conf.d/99-dev.ini <<'EOF'
; Dev di /mnt/c — opcache agresif untuk mengurangi I/O 9P
opcache.enable=1
opcache.memory_consumption=192
opcache.max_accelerated_files=20000
; Tetap cek perubahan file, tapi tidak setiap request (detik)
opcache.revalidate_freq=1
; realpath cache besar = mengurangi stat() ke /mnt/c
realpath_cache_size=4096K
realpath_cache_ttl=600
; Dev friendly
display_errors=On
error_reporting=E_ALL
memory_limit=512M
upload_max_filesize=64M
post_max_size=64M
EOF

  systemctl enable --now php$V-fpm
  systemctl restart php$V-fpm
done

echo "==> Install composer (global, pakai PHP default)"
if ! command -v composer >/dev/null; then
  curl -sS https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer
fi

echo ""
echo "============================================================"
echo "Selesai! Socket PHP-FPM yang tersedia:"
for V in $PHP_VERSIONS; do
  echo "  PHP $V -> unix:/run/php/php$V-fpm.sock"
done
echo ""
echo "Ganti versi CLI default: sudo update-alternatives --config php"
echo "Buat site baru:          sudo bash new-site.sh -p <path> -v <versi> [-r public] [-d domain]"
echo "============================================================"

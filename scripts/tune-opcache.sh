#!/usr/bin/env bash
# ============================================================
# Terapkan tuning opcache ke SEMUA versi PHP-FPM yang sudah
# terinstall di WSL (tanpa install ulang apapun). Contoh:
#   sudo bash /mnt/c/Dev/lokalan/panel/scripts/tune-opcache.sh
# ============================================================
set -euo pipefail

FOUND=0
for DIR in /etc/php/*/fpm; do
  [ -d "$DIR" ] || continue
  V=$(basename "$(dirname "$DIR")")
  FOUND=1

  # Pastikan modul opcache terinstall
  if ! dpkg -l "php$V-opcache" >/dev/null 2>&1; then
    echo "==> Install php$V-opcache"
    apt-get install -y "php$V-opcache"
  fi

  echo "==> Tuning PHP $V -> $DIR/conf.d/99-dev.ini"
  cat > "$DIR/conf.d/99-dev.ini" <<'EOF'
; Dev di /mnt/c — opcache agresif untuk mengurangi I/O 9P
opcache.enable=1
opcache.memory_consumption=192
opcache.max_accelerated_files=20000
; Tetap deteksi perubahan file, tapi maksimal 1x per detik
opcache.revalidate_freq=1
; realpath cache besar = mengurangi stat() ke /mnt/c
realpath_cache_size=4096K
realpath_cache_ttl=600
EOF

  systemctl restart "php$V-fpm"
  echo "    php$V-fpm di-restart"
done

[ "$FOUND" = 1 ] || { echo "Tidak ada PHP-FPM ditemukan di /etc/php/"; exit 1; }

echo ""
echo "==> Verifikasi:"
for DIR in /etc/php/*/fpm; do
  V=$(basename "$(dirname "$DIR")")
  STATUS=$(php$V -r 'echo function_exists("opcache_get_status") && ini_get("opcache.enable") ? "OK" : "TIDAK AKTIF";' 2>/dev/null || echo "?")
  echo "  PHP $V opcache: $STATUS"
done
echo ""
echo "Catatan: verifikasi di atas untuk CLI. Untuk FPM (web), cek dengan"
echo "membuat file phpinfo() dan lihat bagian 'Zend OPcache' -> Enabled."

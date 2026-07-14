# Scripts — Setup Server WSL untuk Lokalan

Script pendukung Lokalan untuk menyiapkan server di WSL: nginx + beberapa versi PHP-FPM jalan bersamaan, membaca kode langsung dari folder Windows via `/mnt/c/...`.

| File | Fungsi |
|---|---|
| `setup.sh` | Install nginx + PHP multi versi (PPA ondrej) + composer + tuning opcache — jalankan sekali |
| `new-site.sh` | Buat nginx site per project (dipanggil Lokalan, bisa juga manual) |
| `tune-opcache.sh` | Terapkan tuning opcache ke PHP yang sudah terinstall sebelumnya |
| `config/.wslconfig` | Template config WSL sisi Windows (`C:\Users\<user>\.wslconfig`) |
| `config/wsl.conf` | Template config WSL sisi Linux (`/etc/wsl.conf`) — systemd wajib aktif |

## Setup awal (sekali per komputer)

```bash
# 1. Config WSL (dari dalam WSL; sesuaikan path ke lokasi project)
sudo cp /mnt/c/Dev/lokalan/panel/scripts/config/wsl.conf /etc/wsl.conf
# + copy config/.wslconfig ke C:\Users\<user>\.wslconfig
# lalu dari PowerShell: wsl --shutdown

# 2. Install server (edit PHP_VERSIONS di dalam script sesuai kebutuhan)
sudo bash /mnt/c/Dev/lokalan/panel/scripts/setup.sh

# Kalau PHP sudah terinstall sebelumnya, cukup:
sudo bash /mnt/c/Dev/lokalan/panel/scripts/tune-opcache.sh
```

## new-site.sh manual (tanpa panel)

```bash
sudo bash new-site.sh -p project-a -v 8.3 -r public      # Laravel -> http://project-a.lo
sudo bash new-site.sh -p clients/kasir -v 7.4 -d kasir.lo # subfolder + custom domain
```

Opsi: `-p` path project (relatif dari `BASE_DIR` di dalam script, atau absolut), `-v` versi PHP, `-r` subdir document root, `-d` custom domain (default `<nama-folder>.lo`). Override base tanpa edit: `SITE_BASE=/mnt/d/Web sudo -E bash new-site.sh ...`

> Catatan: saat dipanggil dari Lokalan, `-p` selalu dikirim sebagai path absolut (dari `base_dir` di `panel.ini`), jadi `BASE_DIR` di script ini tidak perlu disesuaikan.

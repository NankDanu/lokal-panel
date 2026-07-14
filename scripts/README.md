# Scripts — Setup Server WSL buat Lokalan

Ini script pendukung Lokalan buat nyetel server di WSL: nginx + beberapa versi PHP-FPM jalan bareng-bareng, baca kode langsung dari folder Windows via `/mnt/c/...`.

| File | Fungsinya Apa |
|---|---|
| `setup.sh` | Install nginx + PHP multi versi (PPA ondrej) + composer + tuning opcache — jalanin sekali doang |
| `new-site.sh` | Bikin nginx site per project (dipanggil Lokalan, bisa juga manual ente jalanin sendiri) |
| `tune-opcache.sh` | Terapin tuning opcache ke PHP yang udah kepasang sebelumnya |
| `config/.wslconfig` | Template config WSL sisi Windows (`C:\Users\<user>\.wslconfig`) |
| `config/wsl.conf` | Template config WSL sisi Linux (`/etc/wsl.conf`) — systemd wajib aktif |

## Setup awal (sekali doang per komputer)

```bash
# 1. Config WSL (dari dalem WSL; sesuain path ke lokasi repo ente)
sudo cp <lokasi-repo>/scripts/config/wsl.conf /etc/wsl.conf
# + copy config/.wslconfig ke C:\Users\<user>\.wslconfig
# abis itu dari PowerShell: wsl --shutdown

# 2. Install server (edit PHP_VERSIONS di dalem script sesuai kebutuhan ente)
sudo bash <lokasi-repo>/scripts/setup.sh

# Kalo PHP udah kepasang sebelumnya, cukup:
sudo bash <lokasi-repo>/scripts/tune-opcache.sh
```

`<lokasi-repo>` itu path WSL ke folder project ini, misal kalo repo ente ada di `C:\DEV\lokal-panel`, path WSL-nya jadi `/mnt/c/DEV/lokal-panel`.

## new-site.sh manual (tanpa panel)

```bash
sudo bash new-site.sh -p project-a -v 8.3 -r public      # Laravel -> http://project-a.lo
sudo bash new-site.sh -p clients/kasir -v 7.4 -d kasir.lo # subfolder + custom domain
```

Opsi: `-p` path project (relatif dari `BASE_DIR` di dalem script, apa absolut juga boleh), `-v` versi PHP, `-r` subdir document root, `-d` custom domain (default `<nama-folder>.lo`). Mau override base tanpa edit script? Tinggal: `SITE_BASE=/mnt/d/Web sudo -E bash new-site.sh ...`

> Catetan: pas dipanggil dari Lokalan, `-p` selalu dikirim sebagai path absolut (dari `base_dir` di `panel.ini`), jadi `BASE_DIR` di script ini gak usah ente sesuain lagi.

## Mau setup manual step-by-step?

Kalo males jalanin `setup.sh` sekaligus, atau mau ngerti persis apa yang kejadian di tiap langkah (misal buat troubleshoot), cek [CHEATSHEET.md](CHEATSHEET.md) — isinya command satu-satu lengkap keterangan dijalanin di mana (PowerShell/WSL, admin apa engga).

# Cheat Sheet — Setup Manualan Full (Tanpa Panel)

Ini kumpulan command kalo ente mau setup semuanya manual dari nol, tanpa jalanin `setup.sh` sekaligus, atau mau paham step-by-step apa yang sebenernya kejadian di baliknya. Cocok juga kalo mau troubleshoot pas ada yang gagal di tengah jalan.

Tiap command ditandain **dijalanin di mana**, biar gak ketuker:

| Tanda | Artinya |
|---|---|
| 🪟 **PowerShell** | Windows, buka PowerShell biasa |
| 🪟 **PowerShell (Admin)** | Windows, PowerShell "Run as Administrator" |
| 🐧 **WSL** | Terminal Ubuntu di dalem WSL, user biasa |
| 🐧 **WSL (root/sudo)** | Terminal Ubuntu di dalem WSL, pake `sudo` |
| 📝 **Notepad (Admin)** | Notepad dibuka "Run as Administrator" |

---

## 1. Pastiin WSL2 + Ubuntu udah kepasang

🪟 **PowerShell (Admin)**

```powershell
wsl --list --verbose
# Kalo belum ada Ubuntu:
wsl --install -d Ubuntu-24.04
```

Restart komputer kalo diminta.

---

## 2. Seting config WSL (RAM, networking, systemd)

🪟 **PowerShell** — copy template `.wslconfig` ke folder user Windows:

```powershell
copy <lokasi-repo>\scripts\config\.wslconfig $env:USERPROFILE\.wslconfig
```

🐧 **WSL (root/sudo)** — copy template `wsl.conf` ke `/etc/wsl.conf`:

```bash
sudo cp <lokasi-repo>/scripts/config/wsl.conf /etc/wsl.conf
```

> `<lokasi-repo>` itu path ke folder project ini. Kalo di Windows repo-nya `C:\DEV\lokal-panel`, path WSL-nya `/mnt/c/DEV/lokal-panel`.

🪟 **PowerShell** — restart WSL biar config kepake:

```powershell
wsl --shutdown
```

Buka lagi terminal Ubuntu-nya abis ini.

---

## 3. Cek systemd udah aktif

🐧 **WSL**

```bash
systemctl status
```

Kalo error "System has not been booted with systemd", berarti langkah 2 belom kepake bener — cek isi `/etc/wsl.conf`, terus `wsl --shutdown` lagi dari PowerShell.

---

## 4. Install nginx + PPA PHP (ondrej)

🐧 **WSL (root/sudo)**

```bash
sudo apt-get update
sudo apt-get install -y software-properties-common curl
sudo add-apt-repository -y ppa:ondrej/php
sudo apt-get update

sudo apt-get install -y nginx
sudo systemctl enable --now nginx
```

---

## 5. Install PHP multi versi (ulang per versi yang ente mau)

🐧 **WSL (root/sudo)** — contoh buat PHP 8.3, ganti angka versinya sesuai kebutuhan (7.4 / 8.1 / 8.3 / dst):

```bash
V=8.3

sudo apt-get install -y \
  php$V-fpm php$V-cli php$V-mysql php$V-pgsql php$V-sqlite3 \
  php$V-mbstring php$V-xml php$V-curl php$V-zip php$V-gd \
  php$V-intl php$V-bcmath php$V-opcache php$V-redis
```

Ulangin ganti `V=7.4`, `V=8.1`, dst buat versi lain yang ente butuh.

---

## 6. Tuning opcache tiap versi PHP

Penting banget ini, soalnya baca file dari `/mnt/c` itu lambat (I/O lewat 9P), opcache wajib nyala biar gak lelet.

🐧 **WSL (root/sudo)** — bikin file config per versi (ganti `$V` sesuai versi PHP-nya):

```bash
V=8.3

sudo tee /etc/php/$V/fpm/conf.d/99-dev.ini > /dev/null <<'EOF'
opcache.enable=1
opcache.memory_consumption=192
opcache.max_accelerated_files=20000
opcache.revalidate_freq=1
realpath_cache_size=4096K
realpath_cache_ttl=600
display_errors=On
error_reporting=E_ALL
memory_limit=512M
upload_max_filesize=64M
post_max_size=64M
EOF

sudo systemctl enable --now php$V-fpm
sudo systemctl restart php$V-fpm
```

> Kalo PHP-nya udah lama kepasang dan cuma mau apply/perbarui tuning ini ke semua versi sekaligus tanpa install ulang, cukup jalanin `sudo bash scripts/tune-opcache.sh` — udah otomatis loop semua versi yang ketemu di `/etc/php/`.

---

## 7. Install Composer (global)

🐧 **WSL (root/sudo)**

```bash
curl -sS https://getcomposer.org/installer | sudo php -- --install-dir=/usr/local/bin --filename=composer
```

---

## 8. Cek semuanya udah jalan

🐧 **WSL**

```bash
systemctl status nginx
systemctl status php8.3-fpm   # ganti versi sesuai yang diinstall
ls /run/php/                  # harus keliatan php7.4-fpm.sock dst, sesuai versi terinstall
composer --version
```

---

## 9. Bikin site pertama (manual, tanpa panel)

🐧 **WSL (root/sudo)**

```bash
sudo bash <lokasi-repo>/scripts/new-site.sh -p project-a -v 8.3 -r public
```

Detail opsi `-p -v -r -d` ada di [README.md](README.md) folder ini.

---

## 10. Tambahin domain ke hosts (sekali per domain)

📝 **Notepad (Admin)** — buka file:

```
C:\Windows\System32\drivers\etc\hosts
```

Tambahin baris (ganti sesuai domain yang muncul pas bikin site):

```
127.0.0.1  project-a.lo
```

Simpen, terus buka `http://project-a.lo` di browser — kelar.

---

## Ganti versi PHP default buat CLI

🐧 **WSL (root/sudo)**

```bash
sudo update-alternatives --config php
```

## Restart service kalo ada yang aneh

🐧 **WSL (root/sudo)**

```bash
sudo systemctl restart nginx
sudo systemctl restart php8.3-fpm   # ganti versi sesuai yang mau di-restart
```

## Reset WSL total (kalo mentok banget)

🪟 **PowerShell (Admin)**

```powershell
wsl --shutdown
wsl --terminate Ubuntu-24.04
```

> Ini cuma matiin instance WSL, bukan hapus data. Kalo emang mau install ulang dari nol, itu perintah lain (`wsl --unregister`) — dan itu **beneran ngapus semua data di distro**, jangan asal jalanin kalo belum yakin.

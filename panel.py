"""
Lokalan (Lokal Panel) — monitoring & setup nginx + multi PHP-FPM di WSL, dari Windows.
Jalankan: python panel.py  ->  http://127.0.0.1:9000
Konfigurasi per-PC: edit panel.ini (base folder project, distro WSL, port).
"""
import configparser
import re
import shlex
import subprocess
from pathlib import Path
from urllib.parse import unquote

from flask import Flask, render_template, request, make_response

app = Flask(__name__)

# ================= Konfigurasi (panel.ini) =================
_ini = configparser.ConfigParser()
_ini.read(Path(__file__).with_name("panel.ini"), encoding="utf-8")
_cfg = _ini["panel"] if _ini.has_section("panel") else {}

BASE_WIN = _cfg.get("base_dir", r"C:\DEV")          # base folder project di Windows
DISTRO = _cfg.get("distro", "")                       # kosong = distro default WSL
HOSTS_FILE = r"C:\Windows\System32\drivers\etc\hosts"
LISTEN_HOST = _cfg.get("host", "127.0.0.1")
LISTEN_PORT = int(_cfg.get("port", "9000"))

NGX_AVAIL = "/etc/nginx/sites-available"
NGX_ENABLED = "/etc/nginx/sites-enabled"

RE_DOMAIN = re.compile(r"^[a-z0-9][a-z0-9.-]{1,80}$")
RE_PHPVER = re.compile(r"^\d+\.\d+$")
RE_PATH = re.compile(r"^[A-Za-z0-9 _\-./]{1,200}$")
RE_SERVICE = re.compile(r"^(nginx|php[A-Za-z0-9@._-]{0,40})$")
RE_SITENAME = re.compile(r"^[A-Za-z0-9._-]{1,90}$")
RE_NGXFILE = re.compile(r"^/etc/nginx/[A-Za-z0-9._/-]{1,150}$")


def win_to_wsl(p: str) -> str:
    """C:\\DEV -> /mnt/c/DEV"""
    p = p.replace("\\", "/")
    m = re.match(r"^([A-Za-z]):/(.*)$", p)
    return f"/mnt/{m.group(1).lower()}/{m.group(2)}".rstrip("/") if m else p


def wsl_to_win(p: str) -> str:
    m = re.match(r"^/mnt/([a-z])/(.*)$", p)
    return f"{m.group(1).upper()}:\\{m.group(2)}".replace("/", "\\") if m else p


BASE_WSL = win_to_wsl(BASE_WIN)

# Folder scripts (new-site.sh dsb) ikut di dalam project -> portabel antar PC.
# panel.ini `scripts_dir` hanya perlu diisi kalau mau pakai lokasi lain.
SCRIPTS_OVERRIDE = _cfg.get("scripts_dir", "")
SCRIPTS_DIR = SCRIPTS_OVERRIDE or win_to_wsl(str(Path(__file__).with_name("scripts")))


# ================= Helper WSL =================
def wsl(cmd: str, root: bool = True, timeout: int = 60, stdin: str | None = None):
    """Jalankan perintah bash di WSL. Return (rc, stdout, stderr)."""
    args = ["wsl"]
    if DISTRO:
        args += ["-d", DISTRO]
    if root:
        args += ["-u", "root"]
    # /usr/sbin masuk PATH agar `nginx` selalu ketemu (kutip: PATH Windows berisi spasi)
    args += ["--", "bash", "-lc", 'export PATH="$PATH:/usr/sbin:/sbin"; ' + cmd]
    try:
        p = subprocess.run(
            args, capture_output=True, text=True, input=stdin,
            encoding="utf-8", errors="replace", timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", f"Timeout {timeout}s: {cmd}"
    except FileNotFoundError:
        return 1, "", "wsl.exe tidak ditemukan. Pastikan WSL terinstall."


def refresh_sites_response(template, **ctx):
    resp = make_response(render_template(template, **ctx))
    resp.headers["HX-Trigger"] = "refreshSites"
    return resp


# ================= Data collectors =================
def get_services():
    """nginx + semua unit service php* (nama apapun, tidak harus phpX.Y-fpm)."""
    _, out, _ = wsl(
        'echo "nginx|$(systemctl is-active nginx 2>/dev/null)";'
        "systemctl list-units --type=service --all --no-legend --plain 'php*' 2>/dev/null"
        " | awk '{gsub(/\\.service$/,\"\",$1); print $1\"|\"$3}'"
    )
    services = []
    for line in out.splitlines():
        parts = line.split("|")
        if len(parts) == 2 and parts[0]:
            services.append({
                "name": parts[0],
                "status": parts[1] or "?",
                "active": parts[1] == "active",
            })
    return services


def get_nginx_dump():
    """Semua file config yang dimuat nginx, dari `nginx -T`."""
    _, out, _ = wsl("nginx -T 2>/dev/null")
    files, cur, buf = {}, None, []
    for line in out.splitlines():
        m = re.match(r"^# configuration file (.+):\s*$", line.strip())
        if m:
            if cur:
                files[cur] = "\n".join(buf)
            cur, buf = m.group(1), []
        elif cur:
            buf.append(line)
    if cur:
        files[cur] = "\n".join(buf)
    return files


def parse_site_conf(content: str):
    """Ambil server_name, root, versi PHP dari isi sebuah config."""
    def first(pattern):
        for line in content.splitlines():
            line = line.split("#")[0]
            m = re.search(pattern, line)
            if m:
                return m.group(1).rstrip(";")
        return ""
    domain = first(r"^\s*server_name\s+(\S+)")
    root = first(r"^\s*root\s+(\S+)")
    php = ""
    m = re.search(r"php(\d+\.\d+)", content)
    if m:
        php = m.group(1)
    return domain, root, php


def get_php_versions():
    """Gabungan: /etc/php, socket /run/php, dan versi di config nginx."""
    _, out, _ = wsl("ls -1 /etc/php 2>/dev/null; ls -1 /run/php 2>/dev/null")
    vers = set(re.findall(r"(\d+\.\d+)", out))
    for content in get_nginx_dump().values():
        vers.update(re.findall(r"php(\d+\.\d+)", content))
    return sorted(vers)


def get_hosts_domains():
    try:
        text = Path(HOSTS_FILE).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    domains = set()
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        parts = line.split()
        if len(parts) >= 2 and parts[0] in ("127.0.0.1", "::1"):
            domains.update(parts[1:])
    return domains


def add_hosts_entry(domain: str):
    """Tambah '127.0.0.1  domain' ke hosts Windows. Return (ok, pesan).

    Coba tulis langsung dulu (berhasil kalau panel jalan as Administrator).
    Kalau ditolak, jalankan PowerShell elevated -> muncul dialog UAC sekali.
    """
    if domain in get_hosts_domains():
        return True, f"{domain} sudah ada di hosts."
    line = f"127.0.0.1  {domain}"

    # 1) tulis langsung
    try:
        with open(HOSTS_FILE, "a", encoding="utf-8") as fp:
            fp.write(f"\n{line}\n")
        return True, f"{domain} ditambahkan ke hosts."
    except PermissionError:
        pass

    # 2) via UAC (klik Yes di dialog Windows)
    inner = f"Add-Content -LiteralPath '{HOSTS_FILE}' -Value '{line}'"
    inner_sq = inner.replace("'", "''")
    outer = ("Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden "
             f"-ArgumentList '-NoProfile','-Command','{inner_sq}'")
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", outer],
            capture_output=True, text=True, timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        return False, f"Timeout menunggu konfirmasi UAC. Tambahkan manual: {line}"

    if domain in get_hosts_domains():
        return True, f"{domain} ditambahkan ke hosts (via UAC)."
    return False, f"Gagal menulis hosts (UAC dibatalkan?). Tambahkan manual: {line}"


def get_sites():
    """
    Deteksi site dari dua sumber:
    1. Semua file di sites-available (enabled = ada symlink di sites-enabled)
    2. File lain yang dimuat nginx (nginx -T) dan berisi server block (conf.d, include custom)
    """
    hosts = get_hosts_domains()
    dump = get_nginx_dump()
    sites, seen = [], set()

    # --- sumber 1: sites-available (tail memberi header "==> path <==" per file) ---
    _, en_out, _ = wsl(f"ls -1 {NGX_ENABLED} 2>/dev/null")
    enabled_names = set(en_out.split())

    _, out, _ = wsl(f"tail -n +1 {NGX_AVAIL}/* 2>/dev/null")
    avail, cur, buf = {}, None, []
    for line in out.splitlines():
        m = re.match(r"^==> (.+) <==$", line)
        if m:
            if cur:
                avail[cur] = "\n".join(buf)
            cur, buf = m.group(1), []
        elif cur is not None:
            buf.append(line)
    if cur:
        avail[cur] = "\n".join(buf)

    for path, content in sorted(avail.items()):
        name = path.rsplit("/", 1)[-1]
        domain, root, php = parse_site_conf(content)
        sites.append(_site_dict(path, name, domain, root, php,
                                enabled=name in enabled_names, source="avail", hosts=hosts))
        seen.add(name)

    # --- fallback: site enabled yang termuat nginx tapi lolos dari scan di atas ---
    for path, content in dump.items():
        name = path.rsplit("/", 1)[-1]
        if not path.startswith(NGX_ENABLED) or name in seen:
            continue
        domain, root, php = parse_site_conf(content)
        sites.append(_site_dict(f"{NGX_AVAIL}/{name}", name, domain, root, php,
                                enabled=True, source="avail", hosts=hosts))
        seen.add(name)

    # --- sumber 2: config lain yang aktif dimuat nginx (conf.d, include custom) ---
    for path, content in dump.items():
        name = path.rsplit("/", 1)[-1]
        if path.startswith((NGX_AVAIL, NGX_ENABLED)) or name in seen:
            continue
        if not re.search(r"^\s*server\s*\{", content, re.M):
            continue
        domain, root, php = parse_site_conf(content)
        if not (domain or root):
            continue
        sites.append(_site_dict(path, name, domain, root, php,
                                enabled=True, source="include", hosts=hosts))
    return sites


def _site_dict(path, name, domain, root, php, enabled, source, hosts):
    win_root = wsl_to_win(root) if root.startswith("/mnt/") else root
    return {
        "file": path,
        "name": name,
        "log_name": name[:-5] if name.endswith(".conf") else name,
        "domain": domain or "-",
        "root": root or "-",
        "win_root": win_root or "-",
        "php": php or "-",
        "enabled": enabled,
        "source": source,                # avail = bisa toggle/hapus; include = read/edit saja
        "in_hosts": domain in hosts if domain else True,
    }


def sites_context(msg=None, err=None):
    return {"sites": get_sites(), "msg": msg, "err": err}


def list_dirs(rel: str):
    """Daftar subfolder di BASE_WIN/rel (sisi Windows)."""
    rel = rel.strip("/").strip("\\")
    if rel and (not RE_PATH.match(rel) or ".." in rel):
        return None, []
    base = Path(BASE_WIN) / rel.replace("/", "\\") if rel else Path(BASE_WIN)
    try:
        dirs = sorted(
            d.name for d in base.iterdir()
            if d.is_dir() and not d.name.startswith(".")
            and d.name.lower() not in ("node_modules", "vendor", "$recycle.bin")
        )
    except OSError:
        return None, []
    return rel, dirs


# ================= Routes: halaman & partial =================
@app.route("/")
def index():
    return render_template("index.html", php_versions=get_php_versions())


@app.route("/partial/services")
def partial_services():
    return render_template("partials/services.html", services=get_services())


@app.route("/partial/sites")
def partial_sites():
    return render_template("partials/sites.html", **sites_context())


@app.route("/browse")
def browse():
    rel, dirs = list_dirs(request.args.get("path", ""))
    if rel is None:
        return "<div class='text-danger small'>Path tidak valid.</div>"
    parent = "/".join(rel.split("/")[:-1]) if rel else None
    return render_template("partials/browse.html", rel=rel, dirs=dirs, parent=parent)


# ================= Routes: aksi =================
@app.route("/services/restart/<name>", methods=["POST"])
def restart_service(name):
    if RE_SERVICE.match(name):
        wsl(f"systemctl restart {shlex.quote(name)}")
    return render_template("partials/services.html", services=get_services())


@app.route("/sites/create", methods=["POST"])
def create_site():
    path = request.form.get("path", "").strip().replace("\\", "/").strip("/")
    ver = request.form.get("php", "").strip()
    pub = request.form.get("public", "").strip()
    dom = request.form.get("domain", "").strip().lower()

    if not RE_PATH.match(path) or ".." in path:
        return render_template("partials/sites.html", **sites_context(err="Path project tidak valid."))
    if not RE_PHPVER.match(ver):
        return render_template("partials/sites.html", **sites_context(err="Versi PHP tidak valid."))
    if pub and (not RE_PATH.match(pub) or ".." in pub):
        return render_template("partials/sites.html", **sites_context(err="Subdir public tidak valid."))
    if dom and not RE_DOMAIN.match(dom):
        return render_template("partials/sites.html", **sites_context(err="Domain tidak valid."))

    # kirim path absolut WSL, jadi base folder bebas per-PC (panel.ini)
    cmd = f"bash {shlex.quote(SCRIPTS_DIR)}/new-site.sh -p {shlex.quote(BASE_WSL + '/' + path)} -v {ver}"
    if pub:
        cmd += f" -r {shlex.quote(pub)}"
    if dom:
        cmd += f" -d {shlex.quote(dom)}"

    rc, out, errout = wsl(cmd)
    if rc != 0:
        detail = (errout or out).splitlines()
        return render_template("partials/sites.html",
                               **sites_context(err="Gagal: " + (detail[-1] if detail else "unknown")))

    # auto-daftarkan domain ke hosts Windows (dialog UAC muncul jika perlu)
    dom_final = dom or path.split("/")[-1] + ".lo"
    ok, hosts_msg = add_hosts_entry(dom_final)
    if ok:
        return render_template("partials/sites.html", **sites_context(msg=f"Site dibuat. {hosts_msg}"))
    return render_template("partials/sites.html", **sites_context(msg="Site dibuat.", err=hosts_msg))


@app.route("/hosts/add/<domain>", methods=["POST"])
def hosts_add(domain):
    if not RE_DOMAIN.match(domain):
        return render_template("partials/sites.html", **sites_context(err="Domain tidak valid."))
    ok, m = add_hosts_entry(domain)
    return render_template("partials/sites.html",
                           **(sites_context(msg=m) if ok else sites_context(err=m)))


@app.route("/sites/toggle/<name>", methods=["POST"])
def toggle_site(name):
    if not RE_SITENAME.match(name):
        return render_template("partials/sites.html", **sites_context(err="Nama site tidak valid."))
    n = shlex.quote(name)
    _, out, _ = wsl(f"[ -e {NGX_ENABLED}/{n} ] && echo yes || echo no")
    if out == "yes":
        rc, _, err = wsl(f"rm -f {NGX_ENABLED}/{n} && nginx -t && systemctl reload nginx")
        msg, errmsg = (f"Site {name} di-disable.", None) if rc == 0 else (None, f"Gagal disable: {err}")
    else:
        rc, _, err = wsl(f"ln -sf {NGX_AVAIL}/{n} {NGX_ENABLED}/{n} && nginx -t && systemctl reload nginx")
        if rc == 0:
            msg, errmsg = f"Site {name} di-enable.", None
        else:
            wsl(f"rm -f {NGX_ENABLED}/{n}")
            msg, errmsg = None, f"Config tidak valid, enable dibatalkan: {err.splitlines()[-1] if err else '?'}"
    return render_template("partials/sites.html", **sites_context(msg=msg, err=errmsg))


@app.route("/sites/delete/<name>", methods=["POST"])
def delete_site(name):
    if not RE_SITENAME.match(name):
        return render_template("partials/sites.html", **sites_context(err="Nama site tidak valid."))
    n = shlex.quote(name)
    wsl(f"rm -f {NGX_ENABLED}/{n} {NGX_AVAIL}/{n} && nginx -t && systemctl reload nginx")
    return render_template("partials/sites.html", **sites_context(msg=f"Site {name} dihapus."))


# ================= Routes: editor nginx config =================
def _valid_ngx_file(f: str):
    return f and RE_NGXFILE.match(f) and ".." not in f


@app.route("/sites/edit")
def edit_site():
    f = unquote(request.args.get("file", ""))
    if not _valid_ngx_file(f):
        return "<div class='alert alert-danger'>Path config tidak valid.</div>"
    rc, content, err = wsl(f"cat {shlex.quote(f)}")
    if rc != 0:
        return f"<div class='alert alert-danger'>Gagal baca config: {err}</div>"
    return render_template("partials/editor.html", file=f, content=content, msg=None, err=None)


@app.route("/sites/edit", methods=["POST"])
def save_site():
    f = unquote(request.args.get("file", ""))
    if not _valid_ngx_file(f):
        return "<div class='alert alert-danger'>Path config tidak valid.</div>"
    content = request.form.get("content", "")
    if not content.strip():
        return render_template("partials/editor.html", file=f, content=content,
                               msg=None, err="Config kosong — tidak disimpan.")
    q = shlex.quote(f)

    wsl(f"cp {q} {q}.bak")
    rc, _, err = wsl(f"cat > {q}", stdin=content.replace("\r\n", "\n"))
    if rc != 0:
        return render_template("partials/editor.html", file=f, content=content,
                               msg=None, err=f"Gagal menulis: {err}")

    rc, _, err = wsl("nginx -t")
    if rc != 0:
        wsl(f"mv {q}.bak {q}")  # rollback
        detail = "\n".join(err.splitlines()[-2:]) if err else "?"
        return render_template("partials/editor.html", file=f, content=content,
                               msg=None, err=f"nginx -t GAGAL — perubahan di-rollback:\n{detail}")

    wsl(f"rm -f {q}.bak && systemctl reload nginx")
    return refresh_sites_response("partials/editor.html", file=f, content=content,
                                  msg="Tersimpan & nginx di-reload.", err=None)


@app.route("/sites/logs/<name>")
def site_logs(name):
    if not RE_SITENAME.match(name):
        return "<pre>Nama tidak valid.</pre>"
    n = shlex.quote(name)
    _, out, _ = wsl(
        f"tail -n 60 /var/log/nginx/{n}.error.log 2>/dev/null"
        f" || tail -n 60 /var/log/nginx/error.log 2>/dev/null || echo '(log kosong)'"
    )
    return render_template("partials/logs.html", domain=name, log=out or "(log kosong)")


# ================= Routes: pengaturan PHP (php.ini) =================
# Nilai tidak ditulis ke php.ini utama, tapi ke file override conf.d yang
# dimuat paling akhir — aman, dan bisa di-reset dengan menghapus file ini.
PHP_INI_NAME = "99-lokalan.ini"

PHP_COMMON = [
    # (key, label, jenis-validasi)
    ("memory_limit",        "Memory limit",              "size"),
    ("upload_max_filesize", "Upload max filesize",       "size"),
    ("post_max_size",       "Post max size",             "size"),
    ("max_execution_time",  "Max execution time (detik)", "num"),
    ("max_input_time",      "Max input time (detik)",     "num"),
    ("max_input_vars",      "Max input vars",             "num"),
    ("display_errors",      "Display errors",             "onoff"),
    ("date.timezone",       "Timezone",                   "tz"),
]

RE_INI_SIZE = re.compile(r"^\d{1,6}[KMG]?$")
RE_INI_NUM = re.compile(r"^-?\d{1,9}$")
RE_INI_TZ = re.compile(r"^[A-Za-z0-9_/+\-]{1,40}$")
RE_INI_EXTRA = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*\s*=\s*[A-Za-z0-9 ._/'\":%+\-]{0,120}$")


def php_ini_path(ver):
    return f"/etc/php/{ver}/fpm/conf.d/{PHP_INI_NAME}"


def get_php_effective(ver):
    """Nilai efektif setting umum, dibaca dengan konfigurasi FPM."""
    keys = ",".join(k for k, _, _ in PHP_COMMON)
    cmd = (
        f"PHP_INI_SCAN_DIR=/etc/php/{ver}/fpm/conf.d "
        f"php{ver} -c /etc/php/{ver}/fpm/php.ini "
        f"-r \"foreach(explode(',', '{keys}') as \\$k) echo \\$k.'='.ini_get(\\$k).PHP_EOL;\" 2>/dev/null"
    )
    _, out, _ = wsl(cmd)
    vals = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
    return vals


def get_php_extra(ver):
    """Direktif di file override yang di luar daftar umum (ditulis user)."""
    _, out, _ = wsl(f"cat {php_ini_path(ver)} 2>/dev/null")
    known = {k for k, _, _ in PHP_COMMON}
    extra = []
    for line in out.splitlines():
        s = line.strip()
        if not s or s.startswith(";"):
            continue
        if s.split("=", 1)[0].strip() not in known:
            extra.append(s)
    return "\n".join(extra)


@app.route("/php")
def php_settings():
    vers = get_php_versions()
    ver = request.args.get("ver", "")
    if not (RE_PHPVER.match(ver) and ver in vers):
        ver = vers[0] if vers else ""
    return render_template(
        "php.html", versions=vers, ver=ver, fields=PHP_COMMON,
        values=get_php_effective(ver) if ver else {},
        extra=get_php_extra(ver) if ver else "",
        ini_file=php_ini_path(ver) if ver else "", msg=None, err=None,
    )


@app.route("/php", methods=["POST"])
def php_settings_save():
    vers = get_php_versions()
    ver = request.form.get("ver", "")
    if not (RE_PHPVER.match(ver) and ver in vers):
        return render_template("php.html", versions=vers, ver="", fields=PHP_COMMON,
                               values={}, extra="", ini_file="", msg=None,
                               err="Versi PHP tidak valid.")

    lines, errs, values = [], [], {}
    for key, label, kind in PHP_COMMON:
        v = request.form.get(key, "").strip()
        values[key] = v
        if not v:
            continue  # kosong = pakai default php.ini bawaan
        ok = ((kind == "size" and RE_INI_SIZE.match(v))
              or (kind == "num" and RE_INI_NUM.match(v))
              or (kind == "onoff" and v in ("On", "Off"))
              or (kind == "tz" and RE_INI_TZ.match(v)))
        if ok:
            lines.append(f"{key}={v}")
        else:
            errs.append(f"{label}: nilai '{v}' tidak valid")

    extra = request.form.get("extra", "").replace("\r\n", "\n").strip()
    for raw in extra.splitlines():
        s = raw.strip()
        if not s or s.startswith(";"):
            continue
        if RE_INI_EXTRA.match(s):
            lines.append(s)
        else:
            errs.append(f"Direktif tambahan tidak valid: {s}")

    ctx = dict(versions=vers, ver=ver, fields=PHP_COMMON, values=values,
               extra=extra, ini_file=php_ini_path(ver))
    if errs:
        return render_template("php.html", **ctx, msg=None, err="\n".join(errs))

    ini = php_ini_path(ver)
    content = ("; Generated by Lokalan - diedit lewat panel, perubahan manual akan tertimpa\n"
               + "\n".join(lines) + "\n")

    _, had, _ = wsl(f"[ -f {ini} ] && cp {ini} {ini}.bak && echo had || echo new")
    rc, _, err = wsl(f"cat > {ini}", stdin=content)
    if rc != 0:
        return render_template("php.html", **ctx, msg=None, err=f"Gagal menulis: {err}")

    rc, _, err = wsl(f"systemctl restart php{ver}-fpm")
    if rc != 0:
        # rollback ke kondisi sebelumnya, lalu hidupkan lagi
        wsl(f"mv {ini}.bak {ini}" if had == "had" else f"rm -f {ini}")
        wsl(f"systemctl restart php{ver}-fpm")
        _, log, _ = wsl(f"journalctl -u php{ver}-fpm -n 5 --no-pager 2>/dev/null | tail -3")
        return render_template("php.html", **ctx, msg=None,
                               err=f"php{ver}-fpm gagal restart — perubahan di-rollback.\n{log}")

    wsl(f"rm -f {ini}.bak")
    ctx["values"] = get_php_effective(ver)
    ctx["extra"] = get_php_extra(ver)
    return render_template("php.html", **ctx,
                           msg=f"Tersimpan & php{ver}-fpm di-restart.", err=None)


# ================= Debug =================
INI_PATH = Path(__file__).with_name("panel.ini")


RE_WINDIR = re.compile(r'^[A-Za-z]:[\\/][^<>:"|?*\r\n]{0,150}$|^[A-Za-z]:$')
RE_DISTRO = re.compile(r"^[A-Za-z0-9._-]{0,60}$")
RE_WSLPATH = re.compile(r"^/[A-Za-z0-9._/ -]{1,150}$")
RE_HOST = re.compile(r"^[A-Za-z0-9.]{1,40}$")

AUTO_SCRIPTS = win_to_wsl(str(Path(__file__).with_name("scripts")))


def get_wsl_distros():
    """Daftar distro terinstall (output wsl.exe -l adalah UTF-16)."""
    try:
        p = subprocess.run(["wsl", "--list", "--quiet"], capture_output=True,
                           timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        out = p.stdout.decode("utf-16-le", errors="ignore")
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [d.strip() for d in out.replace("\x00", "").splitlines()
            if d.strip() and "docker" not in d.lower()]


def current_settings():
    return {
        "base_dir": BASE_WIN,
        "distro": DISTRO,
        "scripts_dir": SCRIPTS_OVERRIDE,
        "host": LISTEN_HOST,
        "port": LISTEN_PORT,
    }


def write_panel_ini(v):
    INI_PATH.write_text(
        "; Konfigurasi Lokalan (Lokal Panel) — bisa diedit lewat halaman Settings\n"
        "[panel]\n"
        "; Folder development di Windows (path project relatif dari sini)\n"
        f"base_dir = {v['base_dir']}\n"
        "; Nama distro WSL, kosong = default (cek: wsl --list)\n"
        f"distro = {v['distro']}\n"
        "; Folder scripts dilihat dari WSL, kosong = otomatis (./scripts)\n"
        f"scripts_dir = {v['scripts_dir']}\n"
        f"host = {v['host']}\n"
        f"port = {v['port']}\n",
        encoding="utf-8",
    )


@app.route("/settings")
def settings():
    return render_template("settings.html", values=current_settings(),
                           distros=get_wsl_distros(), auto_scripts=AUTO_SCRIPTS,
                           msg=None, err=None)


@app.route("/settings", methods=["POST"])
def save_settings():
    global BASE_WIN, DISTRO, BASE_WSL, SCRIPTS_DIR, SCRIPTS_OVERRIDE

    v = {
        "base_dir": request.form.get("base_dir", "").strip().rstrip("\\/"),
        "distro": request.form.get("distro", "").strip(),
        "scripts_dir": request.form.get("scripts_dir", "").strip().rstrip("/"),
        "host": request.form.get("host", "").strip() or "127.0.0.1",
        "port": request.form.get("port", "").strip() or "9000",
    }

    errs = []
    if not RE_WINDIR.match(v["base_dir"]):
        errs.append(f"Folder development tidak valid: {v['base_dir']}")
    elif not Path(v["base_dir"]).is_dir():
        errs.append(f"Folder tidak ditemukan: {v['base_dir']}")
    if not RE_DISTRO.match(v["distro"]):
        errs.append("Nama distro tidak valid.")
    if v["scripts_dir"] and not RE_WSLPATH.match(v["scripts_dir"]):
        errs.append("Folder scripts harus path WSL (mis. /mnt/c/...) atau kosong.")
    if not RE_HOST.match(v["host"]):
        errs.append("Host tidak valid.")
    if not v["port"].isdigit() or not (1 <= int(v["port"]) <= 65535):
        errs.append("Port harus angka 1–65535.")

    ctx = dict(values=v, distros=get_wsl_distros(), auto_scripts=AUTO_SCRIPTS)
    if errs:
        return render_template("settings.html", **ctx, msg=None, err="\n".join(errs))

    write_panel_ini(v)

    # terapkan langsung tanpa restart (kecuali host/port yang terikat saat start)
    BASE_WIN = v["base_dir"]
    DISTRO = v["distro"]
    BASE_WSL = win_to_wsl(BASE_WIN)
    SCRIPTS_OVERRIDE = v["scripts_dir"]
    SCRIPTS_DIR = SCRIPTS_OVERRIDE or AUTO_SCRIPTS

    note = ""
    if v["host"] != LISTEN_HOST or int(v["port"]) != LISTEN_PORT:
        note = " Perubahan host/port berlaku setelah panel di-restart."
    return render_template("settings.html", **ctx,
                           msg=f"Tersimpan & langsung aktif.{note}", err=None)


@app.route("/readme")
def readme():
    import markdown
    text = Path(__file__).with_name("README.md").read_text(encoding="utf-8")
    html = markdown.markdown(text, extensions=["fenced_code", "tables"])
    return render_template("readme.html", content=html)


@app.route("/debug")
def debug():
    from markupsafe import escape
    lines = [f"DISTRO={DISTRO!r}  BASE_WIN={BASE_WIN!r}  BASE_WSL={BASE_WSL!r}\nSCRIPTS_DIR={SCRIPTS_DIR!r}"]
    for label, cmd in [
        ("whoami", "whoami"),
        ("nginx -v", "nginx -v 2>&1"),
        ("nginx -T count", "nginx -T 2>/dev/null | grep -c 'configuration file'"),
        ("nginx -T head", "nginx -T 2>/dev/null | head -15"),
        ("ls sites-available", "ls -la /etc/nginx/sites-available 2>&1"),
        ("ls sites-enabled", "ls -1 /etc/nginx/sites-enabled 2>&1"),
        ("tail sites-available", "tail -n +1 /etc/nginx/sites-available/* 2>&1 | head -30"),
        ("ls /etc/php + /run/php", "ls /etc/php /run/php 2>&1"),
        ("php units", "systemctl list-units --type=service --all --no-legend --plain 'php*' 2>&1"),
    ]:
        rc, out, err = wsl(cmd)
        lines.append(f"\n===== {label} (rc={rc}) =====\n{out}\n--- stderr ---\n{err}")
    dump = get_nginx_dump()
    lines.append(f"\n===== get_nginx_dump: {len(dump)} file =====\n" + "\n".join(dump))
    sites = get_sites()
    lines.append(f"\n===== get_sites: {len(sites)} site =====\n" + "\n".join(str(s) for s in sites))
    lines.append(f"\n===== get_php_versions =====\n{get_php_versions()}")
    return "<pre>" + str(escape("\n".join(lines))) + "</pre>"


if __name__ == "__main__":
    print(f"Lokalan -> http://{LISTEN_HOST}:{LISTEN_PORT}  (base: {BASE_WIN})")
    app.run(host=LISTEN_HOST, port=LISTEN_PORT, debug=False)

#!/bin/bash
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
release=${1:?Pass the uploaded release directory}
case "$release" in /opt/jiajiao-shop/releases/*) ;; *) exit 2;; esac
id jiajiao >/dev/null 2>&1 || useradd --system --home /var/lib/jiajiao-shop --shell /usr/sbin/nologin jiajiao
install -d -m 750 -o jiajiao -g jiajiao /var/lib/jiajiao-shop
install -d -m 755 /var/www/jiajiao-acme
python3 -m venv /opt/jiajiao-shop/venv
/opt/jiajiao-shop/venv/bin/pip install --disable-pip-version-check -r "$release/jiajiao-shop-backend/requirements.txt"
chown -R root:root "$release"
chmod -R a+rX "$release"
ln -sfn "$release" /opt/jiajiao-shop/current
install -m 644 "$release/jiajiao-shop-backend/deploy/jiajiao-shop.service" /etc/systemd/system/jiajiao-shop.service
systemctl daemon-reload
systemctl enable --now jiajiao-shop.service
systemctl restart jiajiao-shop.service
if [ ! -f /etc/letsencrypt/live/jiajiao.mychangliapp.cn/fullchain.pem ]; then
    install -m 644 "$release/jiajiao-shop-backend/deploy/nginx-http.conf" /etc/nginx/sites-available/jiajiao-shop
    ln -sfn /etc/nginx/sites-available/jiajiao-shop /etc/nginx/sites-enabled/jiajiao-shop
    nginx -t
    systemctl reload nginx
    certbot certonly --webroot -w /var/www/jiajiao-acme -d jiajiao.mychangliapp.cn -d jiajiao-admin.mychangliapp.cn --cert-name jiajiao.mychangliapp.cn --non-interactive
fi
install -m 644 "$release/jiajiao-shop-backend/deploy/nginx.conf" /etc/nginx/sites-available/jiajiao-shop
ln -sfn /etc/nginx/sites-available/jiajiao-shop /etc/nginx/sites-enabled/jiajiao-shop
nginx -t
systemctl reload nginx
install -d -m 755 /etc/letsencrypt/renewal-hooks/deploy
printf '#!/bin/sh\n/usr/sbin/nginx -t && /bin/systemctl reload nginx\n' > /etc/letsencrypt/renewal-hooks/deploy/jiajiao-nginx-reload
chmod 755 /etc/letsencrypt/renewal-hooks/deploy/jiajiao-nginx-reload
systemctl is-active jiajiao-shop.service

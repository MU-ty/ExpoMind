FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html styles.css extras.css app.js manifest.webmanifest sw.js icon.svg /usr/share/nginx/html/
EXPOSE 80

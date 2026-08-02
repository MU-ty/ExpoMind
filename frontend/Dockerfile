FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html styles.css extras.css app.js manifest.webmanifest sw.js icon.svg /usr/share/nginx/html/
COPY assets /usr/share/nginx/html/assets
COPY vendor/mediapipe /usr/share/nginx/html/vendor/mediapipe
EXPOSE 80

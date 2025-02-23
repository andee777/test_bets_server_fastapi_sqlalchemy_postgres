FROM nginx:latest

# Copy custom Nginx configuration files into the image
COPY ./conf.d/default.conf /etc/nginx/conf.d/default.conf
# COPY ./conf.d/ssl.conf /etc/nginx/conf.d/ssl.conf
COPY ./nginx.conf /etc/nginx/nginx.conf

# Create a directory for the Certbot challenge
RUN mkdir -p /var/www/certbot

# Expose both HTTP (80) and HTTPS (443) ports
EXPOSE 80
EXPOSE 443

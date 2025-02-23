# Use the official Certbot image as the base image
FROM certbot/certbot:v2.6.0

# Run Certbot in renew mode in a loop (every 12 hours)
CMD ["sh", "-c", "trap exit TERM; while :; do certbot renew --webroot -w /var/www/certbot; sleep 12h & wait $${!}; done;"]

FROM php:8.2-apache

RUN docker-php-ext-install mysqli pdo pdo_mysql
RUN { \
    echo "output_buffering=4096"; \
    echo "display_errors=On"; \
  } > /usr/local/etc/php/conf.d/edoc.ini

COPY . /var/www/html/

RUN chown -R www-data:www-data /var/www/html

EXPOSE 80

CMD ["apache2-foreground"]

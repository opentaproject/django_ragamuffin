FROM nginx:latest
RUN rm -f /etc/nginx/sites-enabled/default
RUN rm -f /etc/nginx/conf.d/*
COPY nginx.conf /etc/nginx/conf.d
#COPY default.conf /etc/nginx/conf.d

RUN chgrp -R 0 \
  /etc/nginx/conf.d/ \
  /var/cache/ \
  /var/run \
  /var/log/nginx  \
  /srv
#
RUN chmod -R g=u \
  /etc/nginx/conf.d/ \
  /var/cache/ \
  /var/run \
  /var/log/nginx  \
  /srv

RUN chmod -R o+w \
  /etc/nginx/conf.d/ \
  /var/cache/ \
  /var/run \
  /var/log/nginx  \
  /srv

RUN sed -i.bak 's/^user/#user/' /etc/nginx/nginx.conf

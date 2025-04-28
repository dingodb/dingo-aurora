FROM ubuntu:22.04

ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8

RUN apt-get update -y && apt-get install -y --no-install-recommends apt-utils \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    gcc traceroute lsof iputils-ping vim wget curl locales-all\
    python3-pip cmake build-essential python3-dev libxml2-dev supervisor 

COPY . /opt/dingo-aurora


#ENV https_proxy=172.20.3.88:1088
#ENV http_proxy=172.20.3.88:1088

RUN pip install -r /opt/dingo-aurora/requirements.txt


RUN apt-get clean \
    && rm -rf ~/.cache/pip \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /etc/dingoops /var/log/dingoops /var/lib/dingoops

COPY ./etc/gunicorn.py /etc/dingoops/gunicorn.py
COPY ./etc/dingoops.conf /etc/dingoops/dingoops.conf
COPY ./etc/supervisord.conf /etc/dingoops/supervisord.conf
COPY ./docker/start_service.sh /usr/local/bin/start_service.sh
RUN chmod +x /usr/local/bin/start_service.sh

WORKDIR /opt/dingo-aurora


EXPOSE 8887

CMD ["start_service.sh"]

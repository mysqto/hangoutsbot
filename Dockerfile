FROM python:alpine
LABEL description="Google Hangouts Bot"
LABEL maintainer="http://github.com/mysqto/hangoutsbot"
WORKDIR /app
ADD requirements.txt .
RUN pip install -r requirements.txt
RUN mkdir /data
COPY hangupsbot/ ./
VOLUME /data
RUN mkdir -p /root/.local/share && ln -s /data /root/.local/share/hangupsbot
RUN wget -q -O /etc/ssl/cacert.pem https://curl.haxx.se/ca/cacert.pem
RUN apk update && apk upgrade
RUN apk add bash
ADD docker-entrypoint.sh .
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["python", "hangupsbot.py"]
ARG PORTS="9001 9002 9003"
EXPOSE $PORTS

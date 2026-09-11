FROM alpine:3.20

RUN apk add --no-cache iproute2 socat

CMD ["sh", "-c", "\
socat TCP-LISTEN:1883,fork,reuseaddr TCP:mqtt:1883 & \
socat TCP-LISTEN:1884,fork,reuseaddr TCP:mqtt-c1:1883 & \
socat TCP-LISTEN:8883,fork,reuseaddr TCP:mqtt-c2:8883 & \
socat TCP-LISTEN:14840,fork,reuseaddr TCP:host.docker.internal:4840 & \
socat TCP-LISTEN:14841,fork,reuseaddr TCP:host.docker.internal:4841 & \
socat TCP-LISTEN:14842,fork,reuseaddr TCP:host.docker.internal:4842 & \
wait"]

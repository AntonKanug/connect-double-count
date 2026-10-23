# Envoy CONNECT byte double-count

Minimal HTTP/1.1 CONNECT reproducer for Envoy 1.40.0. Requires Docker.

```sh
docker build -t connect-double-count .
docker run --rm --network none connect-double-count
```

The script sends **100 payload bytes each way**. CONNECT adds 71 request-header bytes
and 39 response-header bytes. Expected `upstream_sent`: **171**; `upstream_received`: **139**.
Envoy 1.40.0 counts the payload twice in both upstream counters:

```json
{"upstream_sent": 271, "upstream_received": 239, "downstream_sent": 100}
```

The HTTP codec and TCP proxy both add each payload to the same upstream byte meter.
The downstream counter is correct. All traffic stays on container loopback.

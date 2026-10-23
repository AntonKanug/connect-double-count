#!/usr/bin/env python3
"""Send 100 bytes each way through an Envoy HTTP/1.1 CONNECT tunnel."""
import concurrent.futures
import json
import pathlib
import socket
import subprocess
import tempfile
import time

PAYLOAD = b"x" * 100
HEADERS = b"HTTP/1.1 200 Connection Established\r\n\r\n"


def backend(listener):
    conn, _ = listener.accept()
    with conn:
        conn.settimeout(5)
        request = b""
        while not request.endswith(b"\r\n\r\n"):
            request += conn.recv(1)
        assert request.startswith(b"CONNECT ")
        conn.sendall(HEADERS)
        assert conn.recv(100, socket.MSG_WAITALL) == PAYLOAD
        conn.sendall(PAYLOAD)
        conn.shutdown(socket.SHUT_WR)
        assert conn.recv(1) == b""
        return len(request)


print(subprocess.check_output(["envoy", "--version"], text=True).strip())
with tempfile.TemporaryDirectory() as tmp, socket.socket() as listener:
    listener.bind(("127.0.0.1", 18081))
    listener.listen()
    listener.settimeout(10)
    config = pathlib.Path(tmp, "envoy.yaml")
    access = pathlib.Path(tmp, "access.log")
    config.write_text(f"""
static_resources:
  listeners:
  - address: {{socket_address: {{address: 127.0.0.1, port_value: 18080}}}}
    filter_chains:
    - filters:
      - name: envoy.filters.network.tcp_proxy
        typed_config:
          '@type': type.googleapis.com/envoy.extensions.filters.network.tcp_proxy.v3.TcpProxy
          stat_prefix: tcp
          cluster: connect
          tunneling_config: {{hostname: 'database.example:1433'}}
          access_log:
          - name: envoy.access_loggers.file
            typed_config:
              '@type': type.googleapis.com/envoy.extensions.access_loggers.file.v3.FileAccessLog
              path: {access}
              log_format:
                json_format:
                  upstream_sent: '%UPSTREAM_WIRE_BYTES_SENT%'
                  upstream_received: '%UPSTREAM_WIRE_BYTES_RECEIVED%'
                  downstream_received: '%DOWNSTREAM_WIRE_BYTES_RECEIVED%'
                  downstream_sent: '%DOWNSTREAM_WIRE_BYTES_SENT%'
  clusters:
  - name: connect
    connect_timeout: 2s
    load_assignment:
      cluster_name: connect
      endpoints:
      - lb_endpoints:
        - endpoint:
            address: {{socket_address: {{address: 127.0.0.1, port_value: 18081}}}}
""")
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        serving = pool.submit(backend, listener)
        envoy = subprocess.Popen(["envoy", "-c", str(config), "--concurrency", "1",
                                  "--disable-hot-restart", "--log-level", "error"])
        try:
            for _ in range(100):
                try:
                    client = socket.create_connection(("127.0.0.1", 18080), timeout=5)
                    break
                except ConnectionRefusedError:
                    time.sleep(0.05)
            else:
                raise RuntimeError("Envoy did not start")
            with client:
                client.sendall(PAYLOAD)
                assert client.recv(100, socket.MSG_WAITALL) == PAYLOAD
                assert client.recv(1) == b""
            request_header_size = serving.result(timeout=5)
        finally:
            envoy.terminate()
            envoy.wait(timeout=5)
    result = json.loads(access.read_text())
    assert result["downstream_received"] == 100
    assert result["downstream_sent"] == 100
    print(f"Payload: 100 bytes; HTTP response headers: {len(HEADERS)} bytes")
    print(f"Expected upstream_sent: {100 + request_header_size}")
    print(f"Expected upstream_received: {100 + len(HEADERS)}")
    print(json.dumps(result, indent=2))

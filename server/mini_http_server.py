#!/usr/bin/env python3
"""
Lightweight Standalone HTTP 206 Partial Content Server
Supports byte-range requests for GRUB loopback testing without Nginx/Rust.
"""
import http.server
import socketserver
import os
import re
import sys

PORT = 26001
DIRECTORY = sys.argv[1] if len(sys.argv) > 1 else "."

class RangeHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()
        
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        fs = os.fstat(f.fileno())
        total_len = fs.st_size
        range_header = self.headers.get("Range")

        if not range_header:
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(total_len))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            return f

        match = re.match(r"^bytes=(\d+)-(\d+)?$", range_header)
        if not match:
            self.send_error(416, "Requested Range Not Satisfiable")
            f.close()
            return None

        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else total_len - 1
        end = min(end, total_len - 1)

        if start > end or start >= total_len:
            self.send_error(416, "Requested Range Not Satisfiable")
            f.close()
            return None

        chunk_len = end - start + 1
        f.seek(start)

        self.send_response(206)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Range", f"bytes {start}-{end}/{total_len}")
        self.send_header("Content-Length", str(chunk_len))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        return f

def main():
    print(f"[*] Starting HTTP 206 Range Server on port {PORT}, serving: {DIRECTORY}")
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), RangeHTTPRequestHandler) as httpd:
        httpd.serve_forever()

if __name__ == "__main__":
    main()

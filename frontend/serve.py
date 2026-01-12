#!/usr/bin/env python3
"""Simple static file server for the ABIET UI.
Run with: python serve.py
It will serve the files in this directory on http://0.0.0.0:8080
"""
import http.server
import socketserver
import os

PORT = 8080

class SimpleHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            try:
                with open('index.html', 'rb') as f:
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(f.read())
            except FileNotFoundError:
                self.send_error(404, "File not found")
        else:
            self.send_error(404, "Not found")

    def log_message(self, format, *args):
        pass  # Suppress log messages

# Change to the script's directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

with socketserver.TCPServer(("0.0.0.0", PORT), SimpleHandler) as httpd:
    print(f"Serving UI at http://0.0.0.0:{PORT}")
    httpd.serve_forever()

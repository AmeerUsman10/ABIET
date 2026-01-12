#!/usr/bin/env python3
"""Simple static file server for the ABIET UI.
Run with: python serve.py
It will serve the files in this directory on http://0.0.0.0:8080
"""
import http.server
import socketserver
import pathlib

PORT = 8080
handler = http.server.SimpleHTTPRequestHandler
# Change working directory to the folder containing this script
root = pathlib.Path(__file__).parent
with socketserver.TCPServer(("0.0.0.0", PORT), handler) as httpd:
    print(f"Serving UI at http://0.0.0.0:{PORT}")
    httpd.serve_forever()

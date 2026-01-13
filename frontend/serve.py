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
        # Remove leading slash and handle path traversal
        path = self.path.lstrip('/')
        if not path:
            path = 'index.html'
        
        # Basic security: prevent directory traversal
        if '..' in path or path.startswith('/'):
            self.send_error(403, "Forbidden")
            return
        
        try:
            # Determine content type based on file extension
            if path.endswith('.html'):
                content_type = 'text/html'
            elif path.endswith('.js'):
                content_type = 'application/javascript'
            elif path.endswith('.css'):
                content_type = 'text/css'
            elif path.endswith('.png'):
                content_type = 'image/png'
            elif path.endswith('.jpg') or path.endswith('.jpeg'):
                content_type = 'image/jpeg'
            else:
                content_type = 'text/plain'
            
            with open(path, 'rb') as f:
                self.send_response(200)
                self.send_header('Content-type', content_type)
                self.end_headers()
                self.wfile.write(f.read())
        except FileNotFoundError:
            self.send_error(404, "File not found")
        except Exception as e:
            self.send_error(500, f"Internal server error: {str(e)}")

    def log_message(self, format, *args):
        pass  # Suppress log messages

# Change to the script's directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

with socketserver.TCPServer(("0.0.0.0", PORT), SimpleHandler) as httpd:
    print(f"Serving UI at http://0.0.0.0:{PORT}")
    httpd.serve_forever()

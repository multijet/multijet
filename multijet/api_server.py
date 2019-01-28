from threading import Thread
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from urlparse import urlparse, parse_qs

on_trigger_handler = None


class S(BaseHTTPRequestHandler):
    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_GET(self):
        query_components = parse_qs(urlparse(self.path).query)

        self._set_headers()
        self.wfile.write("ok")
        on_trigger_handler(query_components)


class ApiServer(Thread):
    def __init__(self, on_trigger):
        super(ApiServer, self).__init__()
        global on_trigger_handler
        on_trigger_handler = on_trigger

    def run(self):
        server_address = ('', 6666)
        httpd = HTTPServer(server_address, S)
        print 'Starting ApiServer...'
        httpd.serve_forever()

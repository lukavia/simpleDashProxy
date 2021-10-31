#!/usr/bin/env -S python3 -u
import os
import sys
import signal
from multiprocessing import Process, shared_memory
import time
import psutil

import socketserver
import http.server
import urllib.request
import urllib.error
import urllib.parse
import re

from dashproxy.dashproxy import DashProxy
import logging

logger = logging.getLogger('dash-proxy')
logger.setLevel(logging.INFO)

# Do not follow redirect just return whatever the other server returns
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

opener = urllib.request.build_opener(NoRedirect)
urllib.request.install_opener(opener)

c = shared_memory.SharedMemory(name='simpleDashProxyDownloader', create=True, size=10)

def start_download(url, output_dir):
    d = DashProxy(mpd=url, output_dir=output_dir, download=True, bandwidth_limit=4000000)
    d.run()

class simpleDashProxy(http.server.SimpleHTTPRequestHandler):
    server_version = "simpleDashProxy"
    def do_GET(self):
        res = self.do_request(method='GET')
        if isinstance(res, http.client.HTTPResponse) and res.status == 200:
            length = 64 * 1024
            os.makedirs(os.path.dirname(res.cache_file), exist_ok=True)
            f = open(res.cache_file, mode='wb')
            while True:
                buf = res.read(length)
                if not buf:
                    break
                self.wfile.write(buf)
                f.write(buf)
            f.close()
        else:
            self.copyfile(res, self.wfile)

    def do_HEAD(self):
        self.do_request(method='HEAD')

    def transform_path(self, url):
        # Could be overwritten by implementation
        parts = urllib.parse.urlsplit(url)

        # just 2 level domain, no port
        path = '.'.join(parts.netloc.split('.')[-2:]).split(':')[0]
        # remove session/XXXXXX from path
        path = path + re.sub(r'/session/[^/]*', '', parts.path)

        return path

    def do_request(self, method='GET'):
        # remove the separator so it only leaves http....
        url=self.path.lstrip('/?')

        path = '.cache/'
        path = path + self.transform_path(url)

        if method == 'GET' and os.path.basename(path) == 'manifest.mpd':
            c = shared_memory.SharedMemory(name='simpleDashProxyDownloader')
            pid = int.from_bytes(c.buf, sys.byteorder)
            if pid and psutil.pid_exists(pid):
                pr = psutil.Process(pid)
                pr.terminate()
                pr.wait()
            p = Process(target=start_download, args=(url, os.path.dirname(path)))
            p.start()
            c.buf[:] = p.pid.to_bytes(10, sys.byteorder)
            c.close()

            # Todo sane timeout
            i = 0
            maxTries = 25
            while not os.path.isfile(path) and i < maxTries:
                print('missing file')
                time.sleep(1)
                i = i + 1
            # If we failed to download the mpd, stop the process
            if i == maxTries:
                p.terminate()
                #p.wait()
        if os.path.isfile(path):
            self.path = path
            # Hack to log the request as local file
            self.requestline = path
            return self.send_head()
        else:
            # get the headers and delete the proxy Host
            headers=self.headers
            del headers['Host']
            # Make the request to the server
            req = urllib.request.Request(url, headers=headers, method=method)
            try:
                res = urllib.request.urlopen(req)
            except urllib.error.HTTPError as e:
                res = e
            # Log the request and return the status and headers
            self.log_request(res.status)
            self.send_response_only(res.status)
            # So we can write it later
            res.cache_file = path
            for key, val in res.getheaders():
                self.send_header(key, val)
            self.end_headers()

            # return the result for further processing
            return res

if __name__ == '__main__':
    PORT = 8088

    httpd = socketserver.ForkingTCPServer(('', PORT), simpleDashProxy)
    print ("Now serving at", str(PORT))
    httpd.serve_forever()
    c.unlink()

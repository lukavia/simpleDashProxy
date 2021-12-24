#!/usr/bin/env -S python3 -u
import os.path
import sys
import signal
from multiprocessing import Process
import time
import psutil

import socketserver
import urllib.request
import urllib.error

from simpleProxy.simpleProxy import simpleProxy

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

def start_download(url, output_dir):
    d = DashProxy(mpd=url, output_dir=output_dir, download=True, bandwidth_limit=4000000)
    d.run()

class simpleDashProxy(simpleProxy):
    server_version = "simpleDashProxy"
    downloader_pid = '/dev/shm/simpleDashProxyDownloader.pid'

    def do_request(self, method='GET'):
        # remove the separator so it only leaves http....
        url=self.path.lstrip('/?')

        path = '.cache/'
        path = path + self.transform_path(url)

        if method == 'GET' and os.path.basename(path) == 'manifest.mpd':
            pid = None
            if os.path.exists(self.downloader_pid):
                with open(self.downloader_pid) as f:
                    pid = f.read()
                    if pid:
                        pid = int(pid)
            if pid and psutil.pid_exists(pid):
                pr = psutil.Process(pid)
                pr.terminate()
                pr.wait()
            p = Process(target=start_download, args=(url, os.path.dirname(path)))
            p.start()
            with open(self.downloader_pid, 'w') as f:
                f.write(str(p.pid))

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

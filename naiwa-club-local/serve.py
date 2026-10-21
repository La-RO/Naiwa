"""Local-only, dependency-free HTTP server with video byte-range support."""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from threading import Timer
import webbrowser

ROOT = Path(__file__).resolve().parent


class LocalHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.byte_range = None
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_head(self):
        self.byte_range = None
        requested = self.headers.get('Range')
        path = Path(self.translate_path(self.path)).resolve()
        if requested and path.is_file() and ROOT in path.parents:
            size = path.stat().st_size
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested.strip())
            if not match or (not match[1] and not match[2]):
                self.send_error(416, 'Unsupported range')
                return None
            start = int(match[1]) if match[1] else max(0, size - int(match[2]))
            end = int(match[2]) if match[2] and match[1] else size - 1
            end = min(end, size - 1)
            if start >= size or start > end:
                self.send_response(416)
                self.send_header('Content-Range', f'bytes */{size}')
                self.end_headers()
                return None
            stream = path.open('rb')
            stream.seek(start)
            self.byte_range = (start, end)
            self.send_response(206)
            self.send_header('Content-Type', self.guess_type(str(path)))
            self.send_header('Content-Length', str(end - start + 1))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            return stream
        return super().send_head()

    def copyfile(self, source, outputfile):
        if self.byte_range is None:
            return super().copyfile(source, outputfile)
        remaining = self.byte_range[1] - self.byte_range[0] + 1
        while remaining > 0:
            chunk = source.read(min(64 * 1024, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run the Naiwa Club website locally.')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--no-browser', action='store_true')
    options = parser.parse_args()
    address = f'http://127.0.0.1:{options.port}/'
    try:
        server = ThreadingHTTPServer(('127.0.0.1', options.port), LocalHandler)
    except OSError as error:
        parser.exit(1, f'Could not start the local server: {error}\nTry another port with --port 8080.\n')
    print(f'Naiwa Club is running at {address}\nPress Ctrl+C to stop.', flush=True)
    if not options.no_browser:
        Timer(0.5, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nNaiwa Club local server stopped.')
    finally:
        server.server_close()

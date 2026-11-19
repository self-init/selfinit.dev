#!/usr/bin/env python
"""Dev server: serves output/ and rebuilds when anything in the project
changes (content, templates, static files, icons, config, build code...),
except the build's own output, caches and tool folders. Drafts are
included, so you can preview them before publishing.

Usage: python serve.py [port] [--config FILE]   (default 8000, site.json)
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / 'site.json'
OUTPUT_DIR = ROOT / 'output'      # set from the config in main()
# Folders never watched: tools, caches and docs. The output folder (and its
# .tmp-/.old- siblings) is skipped too.
IGNORE_DIRS = {'.git', '.github', '.venv', '.cache', '__pycache__', 'node_modules', 'docs'}
POLL_SECONDS = 0.5


def snapshot():
    """Map every watched file to its mtime, so any add/edit/delete shows up."""
    state = {}
    output_name = OUTPUT_DIR.name
    for folder, dirs, files in os.walk(CONFIG.parent):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS
                   and not (d == output_name or d.startswith(output_name + '.'))]
        for name in files:
            path = os.path.join(folder, name)
            try:
                state[path] = os.stat(path).st_mtime_ns
            except FileNotFoundError:
                pass  # deleted mid-scan; the next poll will catch it
    return state


def build():
    print(f"[{time.strftime('%H:%M:%S')}] Building...", flush=True)
    # Run as a subprocess so edits to build.py take effect and a broken
    # build doesn't take the server down with it.
    result = subprocess.run([sys.executable, str(ROOT / 'build.py'), '--drafts', '--config', str(CONFIG)], cwd=ROOT)
    if result.returncode != 0:
        print("Build failed; still serving the last good output.", flush=True)


def watch():
    last = snapshot()
    while True:
        time.sleep(POLL_SECONDS)
        current = snapshot()
        if current != last:
            # Wait for a quiet moment so an editor's save burst triggers one build.
            time.sleep(0.1)
            last = snapshot()
            build()


class Handler(SimpleHTTPRequestHandler):
    def send_error(self, code, message=None, explain=None):
        page = OUTPUT_DIR / '404.html'
        if code == 404 and page.is_file():
            body = page.read_bytes()
            self.send_response(404)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)
        else:
            super().send_error(code, message, explain)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # keep the terminal for build output


def main():
    global CONFIG, OUTPUT_DIR
    parser = argparse.ArgumentParser(description='Dev server with rebuild on change.')
    parser.add_argument('port', nargs='?', type=int, default=8000)
    parser.add_argument('--config', type=Path, default=CONFIG, help='site config (default: site.json)')
    args = parser.parse_args()
    port = args.port
    CONFIG = args.config.resolve()
    try:
        OUTPUT_DIR = CONFIG.parent / (json.loads(CONFIG.read_text()).get('output') or 'output')
    except (OSError, ValueError):
        pass  # the build reports a broken config
    build()
    threading.Thread(target=watch, daemon=True).start()

    server = ThreadingHTTPServer(('127.0.0.1', port), partial(Handler, directory=str(OUTPUT_DIR)))
    print(f"Serving on http://127.0.0.1:{port}/ — watching for changes (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

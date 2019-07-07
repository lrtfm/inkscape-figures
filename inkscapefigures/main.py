#!/usr/bin/env python3

import os
import logging
import subprocess
from pathlib import Path
from shutil import copy
# from daemonize import Daemonize
from daemoniker import Daemonizer
import click
import time

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# from .rofi import rofi
import easygui
import pyperclip
from appdirs import user_config_dir

logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))
log = logging.getLogger('inkscape-figures')

def inkscape(path):
    subprocess.Popen(['inkscape', str(path)])


def create_latex(name, title, indent=0):
    lines = [
        r"\begin{figure}[ht]",
        r"    \centering",
        rf"    \incfig{{{name}}}",
        rf"    \caption{{{title.strip()}}}",
        rf"    \label{{fig:{name}}}",
        r"\end{figure}"]

    return '\n'.join(" " * indent + line for line in lines)

user_dir = Path(user_config_dir("inkscape-figures", "Castel"))

if not user_dir.is_dir():
    user_dir.mkdir(parents=True)

roots_flag = user_dir / 'changed.flag'
roots_file =  user_dir / 'roots'
template = user_dir / 'template.svg'
pid_file = user_dir / 'file.pid'

if not roots_file.is_file():
    roots_file.touch()

if not template.is_file():
    source = str(Path(__file__).parent / 'template.svg')
    destination = str(template)
    copy(source, destination)

def add_root(path):
    path = str(path)
    roots = get_roots()
    if path in roots:
        return None

    roots.append(path)
    roots_file.write_text('\n'.join(roots))


def get_roots():
    return [root for root in roots_file.read_text().split('\n') if root != '']

@click.group()
def cli():
    pass

@cli.command()
@click.option('--daemon/--no-daemon', default=True)
def watch(daemon):
    """
    Watches for figures.
    """
    if daemon:
        with Daemonizer() as (is_setup, daemonizer):
            is_parent = daemonizer(str(pid_file))
            if is_parent:
                log.info("parent will done")
        log.info("Watching figures.")
        watch_daemon()
    else:
        log.info("Watching figures.")
        watch_daemon()

class MyHandler(FileSystemEventHandler):
    def on_modified(self, event):
        print(f'event type: {event.event_type}  path : {event.src_path}')
        if event.src_path == str(roots_file):
            if roots_flag.is_file():
                roots_flag.unlink()
            roots_flag.touch()
        else:
            path = Path(event.src_path)
            filename = os.path.basename(event.src_path)

            if path.suffix != '.svg':
                log.debug('File has changed, but is nog an svg')
                return None

            log.info('Recompiling %s', filename)

            pdf_path = path.parent / (path.stem + '.pdf')
            name = path.stem


            command = [
                'inkscape',
                '--export-area-page',
                '--export-dpi', '300',
                '--export-pdf', str(pdf_path),
                '--export-latex', str(path)
            ]

            log.debug('Running command:')
            log.debug(' '.join(str(e) for e in command))

            # Recompile the svg file
            completed_process = subprocess.run(command, shell=True)

            if completed_process.returncode != 0:
                log.error('Return code %s', completed_process.returncode)
            else:
                log.debug('Command succeeded')


            # Copy the LaTeX code to include the file to the cliboard
            pyperclip.copy(create_latex(name, beautify(name)))


def watch_daemon():
    while True:
        log.debug('Loading roots...')
        if roots_flag.is_file():
            roots_flag.unlink()
        event_handler = MyHandler()
        observer = Observer()
        observer.schedule(event_handler, path=str(user_dir), recursive=False)
        roots = get_roots()
        for root in roots:
            observer.schedule(event_handler, path=root, recursive=False)
        log.debug('Start observer...')
        observer.start()
        try:
            while not roots_flag.is_file():
                time.sleep(1)
            observer.stop()
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
        log.debug('end observer...')

@cli.command()
@click.argument('title')
@click.argument(
    'root',
    default=os.getcwd(),
    type=click.Path(exists=True, file_okay=False, dir_okay=True)
)
def create(title, root):
    """
    Creates a figure.

    First argument is the title of the figure
    Second argument is the figure directory.

    """
    title = title.strip()

    file_name = title.replace(' ', '-').lower() + '.svg'
    figures = Path(root).absolute()
    if not figures.exists():
        figures.mkdir()

    figure_path = figures / file_name
    # If a file with this name already exists, append a '2'.
    while figure_path.exists():
        title = title + ' 2'
        file_name = title.replace(' ', '-').lower() + '2.svg'
        figure_path = figures / file_name

    copy(str(template), str(figure_path))
    add_root(figures)
    inkscape(figure_path)

    # Print the code for including the figure to stdout.
    # Copy the indentation of the input.
    leading_spaces = len(title) - len(title.lstrip())
    print(create_latex(figure_path.stem, title, indent=leading_spaces))


def beautify(name):
    return name.replace('_', ' ').replace('-', ' ').title()


@cli.command()
@click.argument(
    'root',
    default=os.getcwd(),
    type=click.Path(exists=True, file_okay=False, dir_okay=True)
)
def edit(root):
    """
    Edits a figure.

    First argument is the figure directory.
    """

    figures = Path(root).absolute()

    # Find svg files and sort them
    files = figures.glob('*.svg')
    files = sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)

    # Open a selection dialog using rofi
    # names = [beautify(f.stem) for f in files]
    selected = easygui.choicebox("Select figure", choices=files)

    if selected:
        path = figures / selected
        add_root(figures)
        print(str(path))
        inkscape(str(path))

if __name__ == '__main__':
    cli()

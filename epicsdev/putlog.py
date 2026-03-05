"""PVAccess text logger server: writes text from PV `dump` to a file."""
# pylint: disable=invalid-name
__version__= 'v0.0.2 26-03-04'

import argparse
import threading

from .epicsdev import Server, init_epicsdev, publish, printi, set_server, serverState, sleep


class C_:
    """Module-local storage."""
    logfile = None
    server = None
    lock = threading.Lock()


def set_dump(value, *_):
    """Append text written to `dump` PV into the selected log file."""
    text = str(value)
    with C_.lock:
        C_.logfile.write(text)
        if not text.endswith("\n"):
            C_.logfile.write("\n")
        C_.logfile.flush()
    publish('dump', text)


def myPVDefs():
    """PV definitions for putlog server."""
    F = 'features'
    T = 'type'
    SET = 'setter'
    return [
        ['dump', 'Text to append to log file', '', {F: 'W', T: str, SET: set_dump}],
    ]


def main():
    """Program entry point."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('logfile', nargs='?', default='/tmp/putlog.log', help=
        'Path to file where text written to the dump PV is appended.')
    parser.add_argument('-p', '--prefix', default='putlog:', help='PV prefix')
    parser.add_argument('-v', '--verbose', action='count', default=0, help=
        'Show more log messages (-vv: more).')
    pargs = parser.parse_args()

    C_.logfile = open(pargs.logfile, 'a', encoding='utf-8')

    pvs = init_epicsdev(pargs.prefix, myPVDefs(), pargs.verbose, listDir='')

    set_server('Start')

    C_.server = Server(providers=[pvs])
    printi(f'Server started with prefix {pargs.prefix}, writing dump text to {pargs.logfile}')
    try:
        while True:
            if serverState().startswith('Exit'):
                break
            sleep()
    finally:
        C_.logfile.close()
        printi('Server has exited')

if __name__ == '__main__':
    main()

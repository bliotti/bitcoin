#!/usr/bin/env python3
import argparse
import contextlib
from fnmatch import fnmatch
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

def usage(args, extras):
    print('Usage: {} [options] tag1 [tag2..tagN]'.format(sys.argv[0]))
    print('Specify release tag(s), e.g.: {} v0.15.1'.format(sys.argv[0]))
    return 0

@contextlib.contextmanager
def pushd(new_dir):
    previous_dir = os.getcwd()
    os.chdir(new_dir)
    try:
        yield
    finally:
        os.chdir(previous_dir)

def download_binary(tag, args):
    if Path(tag).is_dir():
        if not args.remove_dir:
            print('Using cached {}'.format(tag))
            return 0
        shutil.rmtree(tag)
    Path(tag).mkdir()
    bin_path = 'bin/bitcoin-core-{}'.format(tag[1:])
    match = re.compile('v(.*)(rc[0-9]+)$').search(tag)
    if match:
        bin_path = 'bin/bitcoin-core-{}/test.{}'.format(match.group(1),
                                                        match.group(2))
    tarball = 'bitcoin-{tag}-{platform}.tar.gz'.format(tag=tag[1:],
                                                       platform=args.platform)
    url = 'https://bitcoin.org/{bin_path}/{tarball}'.format(bin_path=bin_path,
                                                            tarball=tarball)
    print('Fetching: {url}'.format(url=url))
    cmds = [
        ['curl', '-O', url],
        [ 'tar', '-zxf', tarball, '-C', tag, '--strip-components=1',
                'bitcoin-{tag}'.format(tag=tag[1:]) ],
    ]
    for cmd in cmds:
        ret = subprocess.call(cmd)
        if ret:
            return ret
    Path(tarball).unlink()
    return 0

def build_release(tag, args):
    if args.remove_dir:
        if Path(tag).is_dir():
            shutil.rmtree(tag)
    if not Path(tag).is_dir():
        output = subprocess.check_output(['git', 'tag', '-l', tag])
        if not output:
          print('Tag {} not found'.format(tag))
          return 1
    ret = subprocess.call([
        'git', 'clone', 'https://github.com/bitcoin/bitcoin', tag
    ])
    if ret:
        return ret
    with pushd(tag):
        ret = subprocess.call(['git', 'checkout', tag])
        if ret:
            return ret
        host = args.host
        if args.depends:
            with pushd('depends'):
                no_qt = ''
                if args.functional_tests:
                    no_qt = 'NO_QT=1'
                ret = subprocess.call(['make', no_qt])
                if ret:
                    return ret
                host = os.environ.get('HOST',
                                  subprocess.check_output(['./config.guess']))
        config_flags = '--prefix={pwd}/depends/{host} '.format(
                        pwd=os.getcwd(),
                        host=host) + args.config_flags
        cmds = [
            './autogen.sh',
            './configure {}'.format(config_flags),
            'make',
        ]
        for cmd in cmds:
            ret = subprocess.call(cmd.split())
            if ret:
                return ret
        # Move binaries, so they're in the same place as in the
        # release download
        Path('bin').mkdir(exist_ok=True)
        files = ['bitcoind', 'bitcoin-cli', 'bitcoin-tx']
        for f in files:
            Path('src/'+f).rename('bin/'+f)
        if args.functional_tests:
            Path('src/qt/bitcoin-qt').rename('bin/bitcoin-qt')
    return 0

def check_host(args):
    args.host = os.environ.get('HOST', subprocess.check_output(
                                './depends/config.guess').decode())
    if args.download_binary:
        platforms = {
            'x86_64-*-linux*': 'x86_64-linux-gnu',
            'x86_64-apple-darwin*': 'osx64',
        }
        args.platform = ''
        for pattern, target in platforms.items():
            if fnmatch(args.host, pattern):
                args.platform = target
        if not args.platform:
            print('Not sure which binary to download for {}'.format(args.host))
            return 1
    return 0

def main(args, extras):
    if not extras:
        return usage(args, extras)
    if not Path(args.target_dir).is_dir():
        Path(args.target_dir).mkdir(exist_ok=True, parents=True)
    print("Releases directory: {}".format(args.target_dir))
    ret = check_host(args)
    if ret:
        return ret
    if args.download_binary:
        with pushd(args.target_dir):
            for tag in extras:
                ret = download_binary(tag, args)
                if ret:
                    return ret
        return 0
    args.config_flags = os.environ.get('CONFIG_FLAGS', '')
    if args.functional_tests:
        args.config_flags += ' --without-gui --disable-tests --disable-bench'
    with pushd(args.target_dir):
        for tag in extras:
            ret = build_release(tag, args)
            if ret:
                return ret
    return 0

if __name__=='__main__':
    parser = argparse.ArgumentParser(
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-f', '--functional-tests', action='store_true',
                        help='Configure for functional tests.')
    parser.add_argument('-r', '--remove-dir', action='store_true',
                        help='Remove existing directory.')
    parser.add_argument('-d', '--depends', action='store_true',
                        help='Use depends.')
    parser.add_argument('-b', '--download-binary', action='store_true',
                        help='Download release binary.')
    parser.add_argument('-t', '--target-dir', action='store',
                        help='Target directory.', default='releases')
    args, extras = parser.parse_known_args()
    sys.exit(main(args, extras))

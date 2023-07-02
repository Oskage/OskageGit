import collections
import hashlib
import os
import re
import sys
import zlib
from os import PathLike
from argparse import ArgumentParser, Namespace
from configparser import ConfigParser
from io import BufferedWriter
from math import ceil
from pathlib import Path


class Repository:
    worktree: Path = None
    ogitdir: Path = None
    config: ConfigParser = None
    
    def __init__(self, path: str | bytes | PathLike, force: bool = False):
        path = Path(path)
        self.worktree = path
        self.ogitdir = path / '.ogit'
        
        if not force and not self.ogitdir.is_dir():
            raise Exception(f'Not an OGit repository {self.worktree}')
        
        self.config = ConfigParser()
        config_file = repo_file(self, 'config')
        
        if config_file and config_file.exists():
            self.config.read(config_file)
        elif not force:
            raise Exception('Configuration file is missing')
    
        if not force:
            version = int(self.config.get('core', 
                                          'repositoryformatversion'))
            if version != 0:
                raise Exception('Unsupported repositoryformatversion '
                                f'{version}')


class Object:
    repo: Repository = None
    
    def __init__(self, repo: Repository, data: bytes | None = None):
        self.repo = repo
        
        if data != None:
            self.deserialize(data)
    
    def serialize(self) -> bytes:
        raise NotImplementedError()
    
    def deserialize(self, data: bytes):
        raise NotImplementedError()


class Blob(Object):
    fmt: bytes = b'blob'
    
    def serialize(self) -> bytes:
        return self.blobdata

    def deserialize(self, data: bytes):
        self.blobdata = data


OBJECT_FORMAT_TO_CLASS: dict[bytes, type[Object]] = {
    # b'commit': Commit,
    # b'tree': Tree,
    # b'tag': Tag,
    b'blob': Blob,
}


def read_object(repo: Repository, sha: str) -> Object:
    path = repo_file(repo, 'objects', sha[:2], sha[2:])
    
    with path.open('rb') as f:
        raw = zlib.decompress(f.read())
        
        first_space = raw.find(b' ')
        fmt = raw[:first_space]
        if fmt not in OBJECT_FORMAT_TO_CLASS:
            raise Exception(f'Malformed object {sha}: bad type')
        
        first_null = raw.find(b'\x00', first_space)
        size = int(raw[first_space: first_null].decode())
        if size != len(raw) - first_null - 1:
            raise Exception(f'Malformed object {sha}: bad length')
        
        object_ = OBJECT_FORMAT_TO_CLASS[fmt](repo, raw[first_null + 1:])
        return object_


def find_object(
        repo: Repository, 
        name: str,
        fmt: bytes | None = None,
        follow: bool = True
) -> str:
    return name


def write_object(obj: Object, actually_write: bool = True) -> str:
    data = obj.serialize()
    
    result = obj.fmt + b' ' + str(len(data)).encode() + b'\x00' + data
    sha = hashlib.sha1(result).hexdigest()
    
    if actually_write:
        path = repo_file(obj.repo, 'objects', sha[:2], sha[2:], mkdir=actually_write)
        
        with path.open('wb') as f:
            f.write(zlib.compress(result))
    
    return sha


def hash_object(
        fd: BufferedWriter, 
        fmt: bytes, 
        repo: Repository | None = None
) -> str:
    data = fd.read()
    return write_object(OBJECT_FORMAT_TO_CLASS[fmt](repo, data), 
                        actually_write=repo is not None)    


def repo_default_config() -> ConfigParser:
    config = ConfigParser()
    
    config.add_section('core')
    config.set('core', 'repositoryformatversion', '0')
    config.set('core', 'filemode', 'false')
    config.set('core', 'bare', 'false')
    
    return config


def repo_path(repo: Repository, *path: str | bytes | PathLike) -> Path:
    return repo.ogitdir.joinpath(*path)


def repo_dir(
        repo: Repository, 
        *path: str | bytes | PathLike, 
        mkdir: bool = False
) -> Path | None:
    path: Path = repo_path(repo, *path)
    
    if path.exists():
        if path.is_dir():
            return path
        else:
            raise Exception(f"Not a directory {path}")
    
    if mkdir:
        path.mkdir(parents=True)
        return path
    else:
        return None
        
    
def repo_file(
        repo: Repository, 
        *path: str | bytes | PathLike, 
        mkdir: bool = False
) -> Path | None:
    if repo_dir(repo, *path[:-1], mkdir=mkdir):
        return repo_path(repo, *path)


def create_repo(path: str | bytes | PathLike) -> Repository:
    repo = Repository(path, force=True)
    
    if repo.worktree.exists():
        if not repo.worktree.is_dir():
            raise Exception(f'{path} is not a directory')
        if any(repo.worktree.iterdir()):
            raise Exception(f'path is not empty')
    else:
        repo.worktree.mkdir(parents=True)
    
    assert repo_dir(repo, 'branches', mkdir=True)
    assert repo_dir(repo, 'objects', mkdir=True)
    assert repo_dir(repo, 'refs', 'tags', mkdir=True)
    assert repo_dir(repo, 'refs', 'heads', mkdir=True)
    
    with repo_file(repo, 'description').open('w') as f:
        f.write('Unnamed repository; edit this file "description" to name the '
                'repository.\n')
    
    with repo_file(repo, 'HEAD').open('w') as f:
        f.write('ref: refs/head/master\n')
    
    with repo_file(repo, 'config').open('w') as f:
        config = repo_default_config()
        config.write(f)
    
    return repo


def find_repo(
        path: str | bytes | PathLike = Path('.'), 
        required: bool = True
) -> Repository | None:
    path = Path(path)
    path = path.resolve()
    
    if (path / '.ogit').is_dir():
        return Repository(path)
    
    parent = (path / '..').resolve()
    
    if parent == path:
        if required:
            raise Exception('Not ogit directory')
        else:
            return None
    
    return find_repo(parent, required)


parser = ArgumentParser(description='The OskageGit - content tracker')
subparsers = parser.add_subparsers(title='Commands', dest='command', 
                                   required=True)

COMMAND_TO_SUBPARSER = {
    'init': subparsers.add_parser(
        'init', 
        help='Initialize a new, empty repository'
    ),
    'cat-file': subparsers.add_parser(
        'cat-file', 
        help='Provide content of repository objects.'
    ),
    'hash-object': subparsers.add_parser(
        'hash-object',
        help='Compute object ID and optionally creates a blob from a file.'
    ),
}

COMMAND_TO_SUBPARSER['init'].add_argument(
    'path',
    type=Path,
    metavar='directory', 
    nargs='?', 
    default=Path('.'),
    help='Where to create the repository.',
)

COMMAND_TO_SUBPARSER['cat-file'].add_argument(
    'type',
    type=str,
    metavar='type',
    choices=['blob', 'commit', 'tag', 'tree'],
    help='Specify the type.',
)
COMMAND_TO_SUBPARSER['cat-file'].add_argument(
    'object',
    type=str,
    metavar='object',
    help='The object to display.',
)

COMMAND_TO_SUBPARSER['hash-object'].add_argument(
    '-t',
    type=str,
    metavar='type',
    dest='type',
    choices=['blob', 'commit', 'tag', 'tree'],
    default='blob',
    help='Specify the type.',
)
COMMAND_TO_SUBPARSER['hash-object'].add_argument(
    '-w',
    dest='write',
    action='store_true',
    help='Actually write the object into the database.',
)
COMMAND_TO_SUBPARSER['hash-object'].add_argument(
    'path',
    type=Path,
    help='Read object from <file>.',
)


def cat_file(repo: Repository, obj: str, fmt: bytes = None):
    obj = read_object(repo, find_object(repo, obj, fmt))
    sys.stdout.buffer.write(obj.serialize())


def cmd_cat_file(args: Namespace):
    repo = find_repo()
    cat_file(repo, args.object, fmt=args.type.encode())


def cmd_hash_object(args: Namespace):
    if args.write:
        repo = Repository('.')
    else:
        repo = None
    
    with args.path.open('rb') as fd:
        print(hash_object(fd, args.type.encode(), repo))


def cmd_init(args: Namespace):
    create_repo(args.path)


COMMAND_TO_HANDLER = {
    # 'add': cmd_add,
    'cat-file': cmd_cat_file,
    # 'checkout': cmd_checkout,
    # 'commit': cmd_commit,
    'hash-object': cmd_hash_object,
    'init': cmd_init,
    # 'log': cmd_log,
    # 'ls-files': cmd_ls_files,
    # 'ls-tree': cmd_ls_tree,
    # 'merge': cmd_merge,
    # 'rebase': cmd_rebase,
    # 'rm': cmd_rm,
    # 'show-ref': cmd_show_ref,
    # 'tag': cmd_tag,
}


def main(argv=sys.argv[1:]):
    args = parser.parse_args(argv)
    
    if args.command not in COMMAND_TO_HANDLER:
        raise NotImplementedError()
    
    handler = COMMAND_TO_HANDLER[args.command]
    handler(args)
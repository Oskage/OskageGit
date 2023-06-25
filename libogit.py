from argparse import ArgumentParser, Namespace
import collections
from configparser import ConfigParser
import hashlib
from math import ceil
import os
import re
import sys
import zlib
from pathlib import Path


class Repository:
    worktree = None
    ogitdir = None
    config = None
    
    def __init__(self, path: Path, force: bool = False):
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


def repo_default_config() -> ConfigParser:
    config = ConfigParser()
    
    config.add_section('core')
    config.set('core', 'repositoryformatversion', '0')
    config.set('core', 'filemode', 'false')
    config.set('core', 'bare', 'false')
    
    return config


def repo_path(repo: Repository, *path: Path) -> Path:
    return repo.ogitdir.joinpath(*path)


def repo_dir(
        repo: Repository, 
        *path: Path, 
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
        *path: Path, 
        mkdir: bool = False
) -> Path | None:
    if repo_dir(repo, *path[:-1], mkdir=mkdir):
        return repo_path(repo, *path)


def repo_create(path: Path) -> Repository:
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
    
    with repo_file(repo, 'HEAD').open('w') as f:
        f.write('ref: refs/head/master\n')
    
    with repo_file(repo, 'config').open('w') as f:
        config = repo_default_config()
        config.write(f)
    
    return repo


argparser = ArgumentParser(description='The OskageGit - content tracker')
argsubparsers = argparser.add_subparsers(title='Commands', dest='command')
argsubparsers.required = True
argsp: ArgumentParser = argsubparsers.add_parser(
    name="init", 
    help="Initialize a new, empty repository.",
)

argsp.add_argument(
    'path', 
    type=Path,
    metavar='directory', 
    nargs='?', 
    default=Path('.'),
    help='Where to create the repository.',
)


def cmd_init(args: Namespace):
    repo_create(args.path)


COMMAND_TO_HANDLER = {
    # 'add': cmd_add,
    # 'cat-file': cmd_cat_file,
    # 'checkout': cmd_checkout,
    # 'commit': cmd_commit,
    # 'hash-object': cmd_hash_object,
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
    args = argparser.parse_args(argv)
    
    if args.command not in COMMAND_TO_HANDLER:
        raise NotImplementedError()
    
    handler = COMMAND_TO_HANDLER[args.command]
    handler(args)
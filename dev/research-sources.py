#!/usr/bin/env python3
"""Inspect locked research source packages or export them for review; never install a runtime."""
from pathlib import Path
import argparse
import hashlib
import json
import stat
import sys

ROOT = Path(__file__).resolve().parent.parent
EXPORT_MANIFEST = '.linuxcode-research-export.json'


def check(condition, message):
    if not condition:
        raise ValueError(message)


def relative(name):
    check(isinstance(name, str) and name, 'Expected a nonempty relative path')
    path = Path(name)
    check(not path.is_absolute() and '..' not in path.parts and path.as_posix() == name,
          'Unsafe source path: ' + name)
    return path


def regular(root, name):
    path = root / relative(name)
    cursor = root
    for part in relative(name).parts:
        cursor = cursor / part
        check(not cursor.is_symlink(), 'Refusing symlink: ' + str(cursor))
    check(path.is_file(), 'Source file is absent: ' + str(path))
    return path


class ResearchSources:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.resource = self.root / 'dev/resource-runtime'
        self.lock = json.loads(regular(self.resource, 'overlay.json').read_text())['research_files']

    def locked(self, name):
        check(name in self.lock, 'File is not registered in overlay.json: ' + name)
        path = regular(self.resource, name)
        data = path.read_bytes()
        check(hashlib.sha256(data).hexdigest() == self.lock[name], 'Research source checksum mismatch: ' + name)
        data.decode('utf-8')
        return path, data

    def catalog(self):
        entries = {}
        for name in sorted(self.lock):
            parts = relative(name).parts
            if len(parts) != 5 or parts[0] != 'research' or parts[2:4] != ('payload', 'config') or not parts[4].endswith('-package.json'):
                continue
            _, data = self.locked(name)
            spec = json.loads(data)
            if spec.get('name') != parts[1]:
                continue
            check(parts[1] not in entries, 'Ambiguous source package specification: ' + parts[1])
            readme = 'research/' + parts[1] + '/README.md'
            _, documentation = self.locked(readme)
            entries[parts[1]] = dict(spec=spec, spec_path=name, readme=readme,
                                     title=documentation.decode().splitlines()[0].lstrip('# '))
        return entries

    def select(self, name):
        entries = self.catalog()
        check(name in entries, 'No registered explicit source-package specification for: ' + name)
        entry = entries[name]
        spec = entry['spec']
        sources = spec.get('payload', [])
        check(isinstance(sources, list) and len(set(sources)) == len(sources),
              'Source package payload must be a unique list')
        rows = []
        for source in sources:
            relative(source)
            check(source != EXPORT_MANIFEST, 'Reserved export metadata path')
            attachment = 'research/' + name + '/payload/' + source
            path, data = self.locked(attachment)
            rows.append(dict(path=source, attachment=attachment, sha256=hashlib.sha256(data).hexdigest(),
                             executable=bool(path.stat().st_mode & 0o111)))
        return entry, rows

    def inspect(self, name, workspace=None):
        entry, rows = self.select(name)
        workspace = Path(workspace).expanduser().resolve() if workspace else None
        if workspace:
            check(workspace.is_dir(), 'Workspace directory does not exist')
        for row in rows:
            row['workspace_status'] = 'not_checked'
            if workspace:
                path = workspace / row['path']
                cursor = workspace
                symlink = False
                for part in Path(row['path']).parts:
                    cursor = cursor / part
                    symlink |= cursor.is_symlink()
                if symlink:
                    row['workspace_status'] = 'symlink_review_required'
                elif not path.exists():
                    row['workspace_status'] = 'absent'
                elif not path.is_file():
                    row['workspace_status'] = 'not_a_regular_file'
                else:
                    row['workspace_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                    row['workspace_status'] = 'identical' if row['workspace_sha256'] == row['sha256'] else 'different_review_required'
        references = []
        for reference in entry['spec'].get('reference', []):
            relative(reference)
            attachment = 'research/' + name + '/reference/' + reference + ('' if reference.endswith('.json') else '.json')
            present = (self.resource / attachment).exists()
            if present:
                self.locked(attachment)
            references.append(dict(path=reference, attachment=attachment, available=present))
        return dict(package=name, package_kind='source' if rows else 'evidence_only',
                    documentation='dev/resource-runtime/' + entry['readme'],
                    specification='dev/resource-runtime/' + entry['spec_path'],
                    payload_verified=True, sources=rows, references=references,
                    historical_evidence_complete=all(row['available'] for row in references),
                    workspace=str(workspace) if workspace else None, workspace_files_modified=False,
                    runtime_launched=False, cold_candidate_rebuild_ready=False)

    def export(self, name, output, workspace=None):
        report = self.inspect(name, workspace)
        check(report['sources'], 'Package contains evidence only; use inspect to locate its reports')
        output = Path(output).expanduser()
        check(not output.exists() and not output.is_symlink(), 'Export directory must be new')
        output = output.resolve()
        check(not output.is_relative_to(self.root), 'Export must be outside the distribution checkout')
        if workspace:
            vendor = Path(workspace).expanduser().resolve() / 'vendor'
            check(not output.is_relative_to(vendor), 'Export must not modify workspace vendor sources')
        # Preflight and retain all verified bytes before creating the output.
        payload = []
        for row in report['sources']:
            path, data = self.locked(row['attachment'])
            payload.append((row, data, stat.S_IMODE(path.stat().st_mode)))
        output.mkdir(parents=True, exist_ok=False)
        for row, data, mode in payload:
            path = output / row['path']
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(data)
            path.chmod(mode & 0o777)
        report.update(export=str(output), export_only=True,
                      applying_to_workspace_requires_review=True)
        (output / EXPORT_MANIFEST).write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    listing = commands.add_parser('list', help='List packages with locked explicit source specifications')
    listing.add_argument('--match', default='', help='Filter package names')
    for command in ('inspect', 'export'):
        selected = commands.add_parser(command)
        selected.add_argument('package')
        selected.add_argument('--workspace', type=Path, help='Compare files without changing the workspace')
        if command == 'export':
            selected.add_argument('--output', type=Path, required=True, help='New review directory outside the distribution checkout')
    args = parser.parse_args()
    sources = ResearchSources()
    if args.command == 'list':
        result = {'packages': [dict(name=name, title=entry['title'],
                                    source_files=len(entry['spec']['payload']),
                                    package_kind='source' if entry['spec']['payload'] else 'evidence_only',
                                    documentation='dev/resource-runtime/' + entry['readme'])
                               for name, entry in sources.catalog().items() if args.match in name],
                  'scope': 'Explicit source packages; package names are historical checkpoints, not a runtime upgrade order',
                  'runtime_launched': False, 'cold_candidate_rebuild_ready': False}
    elif args.command == 'inspect':
        result = sources.inspect(args.package, args.workspace)
    else:
        result = sources.export(args.package, args.output, args.workspace)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        print('research sources: ' + str(error), file=sys.stderr)
        raise SystemExit(1) from None

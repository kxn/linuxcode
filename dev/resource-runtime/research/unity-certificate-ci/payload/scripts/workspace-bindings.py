#!/usr/bin/env python3
"""Map private runtime copies into a launcher's already-private workspace mount."""
import json
from pathlib import Path
import subprocess
import sys


def validate(project, rootfs, manifest):
    project = Path(project).resolve(strict=True)
    runtime = project / 'runtime'
    rows = json.loads(Path(manifest).read_text())
    assert isinstance(rows, list) and rows, 'expected nonempty directory mappings'
    mappings = []
    for row in rows:
        assert set(row) == {'source', 'target'}
        source, target = [(project / row[key]).resolve(strict=True)
                          for key in ['source', 'target']]
        for path in [source, target]:
            assert path.is_dir() and path.is_relative_to(runtime) and path != runtime
        assert source != target
        assert not source.is_relative_to(target) and not target.is_relative_to(source)
        for prior_source, prior_target, _ in mappings:
            for path in [source, target]:
                for prior in [prior_source, prior_target]:
                    assert not path.is_relative_to(prior) and not prior.is_relative_to(path)
        destination = Path(rootfs) / 'workspace' / target.relative_to(project)
        assert destination.is_dir()
        mappings.append((source, target, destination))
    return mappings


if __name__ == '__main__':
    # Validate the entire set before the first mount. Any error stops the
    # set -e launcher before any native command can mutate the original cache.
    for source, target, destination in validate(*sys.argv[1:]):
        subprocess.run(['/usr/bin/mount', '--bind', str(source), str(destination)], check=True)
        print('PRIVATE_WORKSPACE_BIND', target.name, flush=True)

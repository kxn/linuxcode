#!/usr/bin/env python3
"""Coalesce identical names only when explicit reexports reach one exact export.

Equal addresses alone are insufficient. The defining provider must itself be
among the original choices; distinct definitions and renamed aliases stay
ambiguous. No implicit whole-library namespace search is performed here.
"""
import hashlib


def verify(image, choices, target, library_root):
    if len(choices) < 2 or len({name for name, _ in choices}) != 1:
        return None
    assert len({tuple(x) for x in choices}) == len(choices)
    chains = []
    for symbol, provider in choices:
        chain = []; seen = set()
        while True:
            identity = provider, symbol
            if identity in seen: raise ValueError('Cyclic equivalent reexport')
            seen.add(identity)
            owner = image(provider); value = owner.exports.get(symbol)
            if value is None: return None
            chain.append(dict(provider=provider, symbol=symbol, export=list(value)))
            if value[0] == 'address':
                if value[1] != target: return None
                break
            if value[0] != 'reexport': raise ValueError('Unknown original export kind')
            if not 1 <= value[1] <= len(owner.dependencies): raise ValueError('Invalid original reexport ordinal')
            provider = owner.dependencies[value[1]-1]; symbol = value[2] or symbol
        chains.append(chain)
    terminal = chains[0][-1]
    if not all(chain[-1] == terminal for chain in chains): return None
    selected = [terminal['symbol'], terminal['provider']]
    if selected not in choices or not any(len(chain) > 1 for chain in chains): return None
    paths = {step['provider'] for chain in chains for step in chain}
    return dict(kind='same-name-explicit-reexports-to-one-defining-export', selected=selected,
        target=hex(target), chains=chains, original_provider_sha256={
            path:hashlib.sha256((library_root/path.lstrip('/')).read_bytes()).hexdigest() for path in sorted(paths)})

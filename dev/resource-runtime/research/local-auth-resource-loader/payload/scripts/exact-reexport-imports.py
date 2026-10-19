#!/usr/bin/env python3
"""Find exact original exports, following only explicit symbol reexport edges.

No nearest-address lookup or alias selection. Each matched chain records all
original provider bytes, so preparation can independently recompute the proof.
"""
import hashlib


def discover(image, dependencies, wanted, library_root):
    exact = {address: [] for address in wanted}
    proofs = []
    hashes = {}

    def follow(provider, symbol, seen):
        identity = provider, symbol
        if identity in seen:
            raise ValueError('Cyclic explicit symbol reexport')
        owner = image(provider)
        value = owner.exports.get(symbol)
        if value is None:
            return None
        step = dict(provider=provider, symbol=symbol, export=list(value))
        if value[0] == 'address':
            return value[1], [step]
        if value[0] != 'reexport':
            raise ValueError('Unknown original export kind')
        ordinal = value[1]
        if not 1 <= ordinal <= len(owner.dependencies):
            raise ValueError('Invalid explicit reexport ordinal')
        result = follow(owner.dependencies[ordinal-1], value[2] or symbol, seen | {identity})
        if result is None:
            return None
        address, chain = result
        return address, [step, *chain]

    for provider in dependencies:
        for symbol in image(provider).exports:
            result = follow(provider, symbol, set())
            if result is None or result[0] not in wanted:
                continue
            address, chain = result
            exact[address].append([symbol, provider])
            if len(chain) > 1:
                proofs.append(dict(target=hex(address), symbol=symbol, provider=provider, chain=chain))
                for step in chain:
                    name = step['provider']
                    if name not in hashes:
                        hashes[name] = hashlib.sha256((library_root/name.lstrip('/')).read_bytes()).hexdigest()
    return exact, dict(chains=proofs, original_provider_sha256=hashes)

#!/usr/bin/env python3
"""Find exact original exports through declared symbol/library reexport edges.

No nearest-address lookup or alias selection. Each matched chain records all
original provider bytes, so preparation can independently recompute the proof.
"""
import hashlib


def discover(image, dependencies, wanted, library_root, whole_library_providers=()):
    assert len(whole_library_providers)==len(set(whole_library_providers))
    assert set(whole_library_providers)<=set(dependencies)
    exact = {address: [] for address in wanted}
    proofs = []
    hashes = {}

    def follow(provider, symbol, seen, allow_whole):
        identity = provider, symbol
        if identity in seen:
            raise ValueError('Cyclic explicit symbol reexport')
        owner = image(provider)
        value = owner.exports.get(symbol)
        if value is None:
            if allow_whole:
                # Preserve the original LC_REEXPORT_DYLIB lookup order. A
                # regular LC_LOAD_DYLIB never exposes its child's namespace.
                for dependency in owner.reexports:
                    assert dependency in owner.dependencies
                    result=follow(dependency,symbol,seen|{identity},True)
                    if result is not None:
                        address,chain=result
                        step=dict(provider=provider,symbol=symbol,kind='whole-library-reexport',
                                  dependency=dependency,ordinal=owner.dependencies.index(dependency)+1)
                        return address,[step,*chain]
            return None
        step = dict(provider=provider, symbol=symbol, export=list(value))
        if value[0] == 'address':
            return value[1], [step]
        if value[0] != 'reexport':
            raise ValueError('Unknown original export kind')
        ordinal = value[1]
        if not 1 <= ordinal <= len(owner.dependencies):
            raise ValueError('Invalid explicit reexport ordinal')
        result = follow(owner.dependencies[ordinal-1], value[2] or symbol, seen | {identity}, allow_whole)
        if result is None:
            return None
        address, chain = result
        return address, [step, *chain]

    def names(provider,seen):
        if provider in seen:raise ValueError('Cyclic whole-library reexport namespace')
        owner=image(provider);result=set(owner.exports)
        for dependency in owner.reexports:
            assert dependency in owner.dependencies
            result.update(names(dependency,seen|{provider}))
        return result

    for provider in dependencies:
        allow_whole=provider in whole_library_providers
        symbols=list(image(provider).exports)
        if allow_whole:
            symbols+=sorted(names(provider,set())-set(symbols))
        for symbol in symbols:
            result = follow(provider, symbol, set(), allow_whole)
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
    proof=dict(chains=proofs, original_provider_sha256=hashes)
    if whole_library_providers:proof['whole_library_providers']=list(whole_library_providers)
    return exact,proof

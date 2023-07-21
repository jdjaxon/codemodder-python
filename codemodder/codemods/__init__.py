from codemodder.codemods.secure_random import SecureRandom
from codemodder.codemods.url_sandbox import UrlSandbox
from codemodder.codemods.process_creation_sandbox import ProcessSandbox

DEFAULT_CODEMODS = {SecureRandom, UrlSandbox, ProcessSandbox}
ALL_CODEMODS = DEFAULT_CODEMODS


def match_codemods(codemod_include: list, codemod_exclude: list):
    if not codemod_include and not codemod_exclude:
        return {codemod.METADATA.NAME: codemod for codemod in DEFAULT_CODEMODS}

    # cli should've already prevented both include/exclude from being set.
    assert codemod_include or codemod_exclude

    if codemod_exclude:
        return {
            name: codemod
            for codemod in DEFAULT_CODEMODS
            if (name := codemod.METADATA.NAME) not in codemod_exclude
        }

    return {
        name: codemod
        for codemod in DEFAULT_CODEMODS
        if (name := codemod.METADATA.NAME) in codemod_include
    }

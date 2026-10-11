#!/usr/bin/env python3
"""Build pinned wimlib with metadata-preserving replacement for plain files.

Source modification is opt-in via TINY11_PRESERVE_METADATA=1 and refuses
hard-linked, reparse, or multi-stream files. The patch retains upstream LGPL
licensing; the upstream copyright header is unchanged.
"""
import argparse
from pathlib import Path
import subprocess

REVISION = "cd5e231c348c255ae5088873b5a66ee0eb96fa07"
ANCHOR = "\t\tret = journaled_unlink(j, existing);\n"
PATCH = '''
		/* Tiny11 macOS: keep Windows metadata when replacing a plain file. */
		if (getenv("TINY11_PRESERVE_METADATA")) {
			struct wim_inode *old = existing->d_inode;
			struct wim_inode *new = branch->d_inode;
			if (old->i_nlink != 1 || old->i_num_streams != 1 ||
			    (old->i_attributes & (FILE_ATTRIBUTE_REPARSE_POINT |
			                          FILE_ATTRIBUTE_ENCRYPTED))) {
				ERROR("Metadata-preserving replacement requires a plain, single-link, single-stream file");
				return WIMLIB_ERR_UNSUPPORTED;
			}
			new->i_attributes = old->i_attributes;
			new->i_security_id = old->i_security_id;
			new->i_creation_time = old->i_creation_time;
			new->i_last_access_time = old->i_last_access_time;
			new->i_last_write_time = old->i_last_write_time;
			new->i_unknown_0x54 = old->i_unknown_0x54;
			if (old->i_extra) {
				struct wim_inode_extra *extra = MALLOC(sizeof(*extra) + old->i_extra->size);
				if (!extra) return WIMLIB_ERR_NOMEM;
				memcpy(extra, old->i_extra, sizeof(*extra) + old->i_extra->size);
				FREE(new->i_extra);
				new->i_extra = extra;
			}
			if (existing->d_short_name_nbytes) {
				utf16lechar *name = MALLOC(existing->d_short_name_nbytes + 2);
				if (!name) return WIMLIB_ERR_NOMEM;
				memcpy(name, existing->d_short_name, existing->d_short_name_nbytes + 2);
				FREE(branch->d_short_name);
				branch->d_short_name = name;
				branch->d_short_name_nbytes = existing->d_short_name_nbytes;
			}
		}
'''


def run(args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--prefix', type=Path, required=True)
    args = parser.parse_args()
    source, prefix = args.source.resolve(), args.prefix.resolve()
    if not source.exists():
        run(['git', 'clone', 'https://github.com/ebiggers/wimlib.git', str(source)])
        run(['git', 'checkout', '--detach', REVISION], source)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
    if revision != REVISION:
        raise RuntimeError(f'Expected wimlib revision {REVISION}, got {revision}')
    file = source / 'src/update_image.c'
    text = file.read_text()
    if '#include <stdlib.h>' not in text:
        text = text.replace('#include <errno.h>', '#include <errno.h>\n#include <stdlib.h>')
    if 'Tiny11 macOS: keep Windows metadata' not in text:
        if text.count(ANCHOR) != 1:
            raise RuntimeError('Wimlib patch anchor is not unique')
        text = text.replace(ANCHOR, PATCH + ANCHOR)
    file.write_text(text)
    run(['./bootstrap'], source)
    run(['./configure', '--without-fuse', '--without-ntfs-3g', '--disable-shared',
         '--prefix=' + str(prefix)], source)
    run(['make', '-j4'], source)
    run(['make', 'install'], source)


if __name__ == '__main__':
    main()

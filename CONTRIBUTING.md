# Contributing

The macOS port lives in `macos/`. Read `macos/BUILD.md` and `macos/PARITY.md` before changing the image pipeline. Keep upstream-derived choices tied to the audited commit and SHA-256 in `macos/config.py`.

Before opening a pull request, run:

```sh
cd macos
python3 -m py_compile ./*.py tools/*.py
python3 -m unittest discover -s tests -v
```

Changes to WIM hives or setup files need read-back and Windows metadata validation. Clearly distinguish local structural checks from Windows target tests. Don't label deferred DISM servicing as passed until it's verified on Windows.

Please don't commit Windows installation media, WIM/ESD/SWM images, product keys, local build reports, test hives, credentials, or personal build paths. A macOS integration build needs the prerequisites in `macos/BUILD.md` and should use background priority and low compression thread counts.

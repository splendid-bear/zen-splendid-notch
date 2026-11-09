.PHONY: help install uninstall install-mod uninstall-mod test
.DEFAULT_GOAL := help
PYTHON ?= python3
export PROFILE

help:
	@printf '%s\n' 'make install PROFILE="/absolute/path/to/zen/profile"' 'make uninstall PROFILE="/absolute/path/to/zen/profile"' 'Close Zen before native installation or removal:' 'make install-mod PROFILE="/absolute/path/to/zen/profile"' 'make uninstall-mod PROFILE="/absolute/path/to/zen/profile"' 'make test'

install uninstall:
	@$(PYTHON) -c 'import os, sys; from pathlib import Path; from install import update; p = os.environ.get("PROFILE", ""); sys.exit("Set PROFILE to your Zen profile root directory") if not p else update(Path(p).expanduser(), "$@")'

install-mod uninstall-mod:
	@$(PYTHON) native_install.py $(@:-mod=)

test:
	@$(PYTHON) -m unittest -v test_install test_native_install test_package

#!/bin/zsh

PROJECT_DIR="${0:A:h}"
cd "$PROJECT_DIR" || exit 1

# Finder-launched Terminal sessions may not inherit Homebrew's PATH.
BREW="$(command -v brew || true)"
if [[ -z "$BREW" && -x /opt/homebrew/bin/brew ]]; then BREW=/opt/homebrew/bin/brew; fi
if [[ -z "$BREW" && -x /usr/local/bin/brew ]]; then BREW=/usr/local/bin/brew; fi
if [[ -n "$BREW" ]]; then
	BREW_PREFIX="$($BREW --prefix)"
	export PATH="$BREW_PREFIX/bin:$BREW_PREFIX/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
fi

if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' 2>/dev/null; then
	if [[ -z "$BREW" ]]; then
		print "Python 3.10+ and Homebrew are required. Install Homebrew from https://brew.sh, then open this file again."
		read "?Press Return to close this window. "
		exit 1
	fi
	print "Installing Python 3.10+ with Homebrew…"
	"$BREW" install python || exit 1
	BREW_PREFIX="$($BREW --prefix)"
	export PATH="$BREW_PREFIX/bin:$BREW_PREFIX/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
	if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
		print "Homebrew Python 3.10+ is unavailable on PATH."
		read "?Press Return to close this window. "
		exit 1
	fi
fi

python3 build-wizard.py
RESULT=$?
print ""
if [[ $RESULT -ne 0 ]]; then print "The build did not finish. Read the message above for the next step."; fi
read "?Press Return to close this window. "
exit $RESULT

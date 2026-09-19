#!/usr/bin/env bash
# Build one release of Clause: the server package and the site package,
# from one checkout, with one version. Run from anywhere:
#
#     bash deploy/release.sh
#
# Produces, next to the source tree:
#     clause-<version>.tar.gz     the server: readable source, deploy files,
#                                 tests; install with deploy/install.sh
#     clause-site-<version>.zip   the site for Netlify: minified, obfuscated
#                                 page, translations, Leaflet, the Privy bundle
#     RELEASE-<version>.md        what is in it and how to install it
#
# The tests run first; a release is not built from a tree that fails them.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$(cd "$HERE/.." && pwd)"
VERSION="$(python3 -c "import re,pathlib; print(re.search(r'__version__ = \"([^\"]+)\"', pathlib.Path('$HERE/clause/__init__.py').read_text()).group(1))")"

echo "==> clause $VERSION"
echo "==> tests"
(cd "$HERE" && python3 -m pytest -q -p no:cacheprovider -x)

echo "==> site"
(cd "$HERE" && python3 site/build.py)

echo "==> packages"
rm -f "$OUT/clause-$VERSION.tar.gz" "$OUT/clause-site-$VERSION.zip"
tar -C "$OUT" --exclude='__pycache__' --exclude='.pytest_cache' --exclude='clause/hazard_build' \
    --exclude='clause/privy-bundle/node_modules' --exclude='clause/site/dist' \
    -czf "$OUT/clause-$VERSION.tar.gz" clause
(cd "$HERE/site/dist" && zip -qr "$OUT/clause-site-$VERSION.zip" .)

cat > "$OUT/RELEASE-$VERSION.md" <<EOF
# Clause $VERSION

Two files, one version. Both must be installed together: the site talks to
the API by version and an old page against a new server (or the reverse)
will show errors.

## Server (api.clause.insure)

    scp clause-$VERSION.tar.gz root@YOUR-SERVER:/root/
    ssh root@YOUR-SERVER 'tar xzf clause-$VERSION.tar.gz && cd clause && sudo bash deploy/install.sh api.clause.insure you@example.com'

The installer keeps /etc/clause/clause.env and /var/lib/clause; the book is
reloaded on start. Check with:

    curl -s https://api.clause.insure/api/health

which must report "version": "$VERSION".

## Site (clause.insure on Netlify)

Upload clause-site-$VERSION.zip as a deploy (Deploys > drag and drop, or the
Netlify CLI). It contains the built page only; the readable source is in the
server package and is not published.

## What changed

See CHANGELOG.md inside the server package.
EOF

ls -la "$OUT/clause-$VERSION.tar.gz" "$OUT/clause-site-$VERSION.zip" "$OUT/RELEASE-$VERSION.md"

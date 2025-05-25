#!/usr/bin/env bash
zip oma.pyz *.py
echo '#!/usr/bin/env python3' | cat - oma.pyz > oma
cp oma oma.pyz
chmod +x oma
chmod +x oma.pyz
./oma --help
./oma.pyz --version
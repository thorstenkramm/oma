#!/usr/bin/env bash
zip oma.zip *.py
mv oma.zip oma.pyz
echo '#!/usr/bin/env python3' | cat - oma.pyz > oma
cp oma oma.pyz
chmod +x oma
chmod +x oma.pyz
./oma --help
./oma.pyz --version
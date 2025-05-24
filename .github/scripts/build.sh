#!/usr/bin/env bash
zip oma.pyz *.py VERSION
echo '#!/usr/bin/env python3' | cat - oma.pyz > oma
chmod +x oma
./oma --help
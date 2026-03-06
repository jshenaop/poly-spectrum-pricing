import sys
from pathlib import Path

# Asegura que el directorio raiz del proyecto este en sys.path
# para que "from app.xxx import ..." funcione desde tests/
sys.path.insert(0, str(Path(__file__).parent))

"""Third-party reference data: GeoNames (places) and Natural Earth (country and admin-1 borders).

Downloaded once into ``$WHITEXMAS_DATA/external/`` with a manifest of URLs and SHA-256.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from .download import sha256_file

log = logging.getLogger(__name__)

GEONAMES = "https://download.geonames.org/export/dump/"
SOURCES = {
    "cities15000.zip": GEONAMES + "cities15000.zip",
    "admin1CodesASCII.txt": GEONAMES + "admin1CodesASCII.txt",
    "countryInfo.txt": GEONAMES + "countryInfo.txt",
    "alternateNamesV2.zip": GEONAMES + "alternateNamesV2.zip",
    "ne_10m_admin_0_countries.zip": "https://naciscdn.org/naturalearth/10m/cultural/"
    "ne_10m_admin_0_countries.zip",
    "ne_10m_admin_1_states_provinces.zip": "https://naciscdn.org/naturalearth/10m/cultural/"
    "ne_10m_admin_1_states_provinces.zip",
}
USER_AGENT = "whitexmas-pipeline/0.1 (+https://github.com/Kochal/white_xmas)"


def fetch(name: str, ext_dir: Path, retries: int = 4) -> Path:
    target = ext_dir / name
    man_path = ext_dir / "manifest.json"
    man = json.loads(man_path.read_text()) if man_path.exists() else {}
    if target.exists() and man.get(name, {}).get("sha256") == sha256_file(target):
        return target
    ext_dir.mkdir(parents=True, exist_ok=True)
    url = SOURCES[name]
    tmp = target.with_suffix(target.suffix + ".part")
    for attempt in range(1, retries + 1):
        try:
            log.info("downloading %s", url)
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                while b := r.read(1 << 20):
                    f.write(b)
            break
        except Exception as e:  # noqa: BLE001
            if attempt == retries:
                raise
            log.warning("%s: %s; retrying", name, e)
    tmp.replace(target)
    man[name] = {
        "url": url,
        "sha256": sha256_file(target),
        "bytes": target.stat().st_size,
        "downloaded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    man_path.write_text(json.dumps(man, indent=2, sort_keys=True))
    return target

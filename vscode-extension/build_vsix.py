"""Build mike-bridge-<version>.vsix from package.json and extension.js.

    python vscode-extension/build_vsix.py

A .vsix is a zip: a manifest, a content-types file and the extension's own
files under extension/. Made here with the standard library, so shipping the
editor half of Mike needs no npm tooling. Older builds are removed, leaving
the one ide/install.py and packaging/mike.spec ship.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent

_CONTENT_TYPES = """<?xml version="1.0" encoding="utf-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="json" ContentType="application/json" />
  <Default Extension="js" ContentType="application/javascript" />
  <Default Extension="vsixmanifest" ContentType="text/xml" />
  <Default Extension="md" ContentType="text/markdown" />
</Types>
"""


def _manifest(pkg: dict) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="{escape(pkg['name'])}" Version="{escape(pkg['version'])}" Publisher="{escape(pkg['publisher'])}" />
    <DisplayName>{escape(pkg['displayName'])}</DisplayName>
    <Description xml:space="preserve">{escape(pkg['description'])}</Description>
    <Tags></Tags>
    <Categories>{escape(', '.join(pkg.get('categories', [])))}</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties>
      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{escape(pkg['engines']['vscode'])}" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value="" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value="" />
      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="ui,workspace" />
    </Properties>
  </Metadata>
  <Installation>
    <InstallationTarget Id="Microsoft.VisualStudio.Code" />
  </Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />
  </Assets>
</PackageManifest>
"""


def build() -> Path:
    pkg = json.loads((HERE / "package.json").read_text(encoding="utf-8"))
    out = HERE / f"{pkg['name']}-{pkg['version']}.vsix"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("extension.vsixmanifest", _manifest(pkg))
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.write(HERE / "package.json", "extension/package.json")
        z.write(HERE / "extension.js", "extension/extension.js")
    for old in HERE.glob(f"{pkg['name']}-*.vsix"):
        if old != out:
            old.unlink()
    return out


if __name__ == "__main__":
    print(build())

"""Mike's own installer.

Deliberately NOT under packaging/: adding an __init__.py there turned the
repo's packaging folder into an importable package that shadowed the real
`packaging` library, which PyInstaller and setuptools both import. The build
died with "No module named 'packaging.requirements'". A directory named
after a PyPI package must not become one.
"""

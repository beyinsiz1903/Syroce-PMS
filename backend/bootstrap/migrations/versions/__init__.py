"""Migration versiyonları paketi.

Her ``v*.py`` modülü modül seviyesinde bir ``MIGRATION`` (``Migration`` örneği)
tanımlar. ``registry.discover_migrations`` bunları otomatik keşfeder ve
``version`` sırasına göre uygular.
"""

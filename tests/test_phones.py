"""El alias 521 y los 10 dígitos salen de un solo módulo."""
from app.phones import canonical, last10


def test_el_alias_mexicano_de_13_digitos_se_vuelve_52():
    assert canonical("5216671020672") == "526671020672"
    assert canonical("+52 1 667 102 0672") == "526671020672"
    assert canonical("526671020672") == "526671020672"
    assert canonical(None) == ""


def test_los_ultimos_10_digitos_ignoran_el_prefijo():
    assert last10("5216671020672") == "6671020672"
    assert last10("526671020672") == "6671020672"
    assert last10("6671020672") == "6671020672"
    assert last10("12345") == "12345"
    assert last10(None) == ""

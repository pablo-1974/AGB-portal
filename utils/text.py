import unicodedata


def normalize_for_sort(text: str) -> str:
    """
    Normaliza para ordenar como en español: ignora mayúsculas/minúsculas y tildes (á≈a).
    """
    if not text:
        return ""

    normalized = unicodedata.normalize("NFD", text)
    without_accents = "".join(
        c for c in normalized if unicodedata.category(c) != "Mn"
    )

    return without_accents.casefold()

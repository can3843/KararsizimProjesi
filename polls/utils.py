import secrets
import string

_PUBLIC_ID_ALPHABET = string.ascii_letters + string.digits


def generate_public_id(length=11):
    return "".join(secrets.choice(_PUBLIC_ID_ALPHABET) for _ in range(length))


def compute_percentages(counts):
    """Yüzdeleri yuvarlar; toplam 100'den sapıyorsa farkı en büyük seçeneğe ekler."""
    total = sum(counts)
    if total == 0:
        return [0] * len(counts)
    percents = [round(count * 100 / total) for count in counts]
    percents[counts.index(max(counts))] += 100 - sum(percents)
    return percents


def decision_badge(percents, total, is_open=True):
    """Kararsızlık rozeti: (seviye, metin). Fark, en çok oy alan iki seçenek arasındadır."""
    if total == 0:
        return "empty", "İlk oyu sen ver" if is_open else "Kimse oy vermedi"
    first, second = sorted(percents, reverse=True)[:2]
    gap = first - second
    if gap <= 5:
        return "split", "Kalabalık da kararsız"
    if gap <= 20:
        return "close", "Az farkla önde"
    return "clear", "Karar net"

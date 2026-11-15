"""PII masking tests: Presidio defaults plus the CNIC and Pakistani phone recognizers."""

import pytest

from guard.pii import get_masker


@pytest.mark.parametrize("text,raw", [
    ("mera cnic 35202-1234567-1 hai", "35202-1234567-1"),
    ("shanakhti card number 3520212345671 likh lo", "3520212345671"),
])
def test_cnic_masked(text: str, raw: str) -> None:
    """Dashed and plain (with context) CNIC numbers are masked."""
    out = get_masker().mask(text)
    assert raw not in out and "<PK_CNIC>" in out


@pytest.mark.parametrize("raw", ["0300-1234567", "03001234567", "+92 300 1234567", "+923001234567",
                                 "0092-321-7654321", "042-35761234"])
def test_pk_phone_masked(raw: str) -> None:
    """Pakistani mobile and landline formats are masked."""
    out = get_masker().mask(f"mujhe is number pe call karo {raw} shukriya")
    assert raw not in out


def test_email_masked() -> None:
    """Email addresses are masked by Presidio's default recognizer."""
    out = get_masker().mask("report ali.khan@example.com pe bhej do")
    assert "ali.khan@example.com" not in out and "<EMAIL_ADDRESS>" in out


def test_text_without_pii_unchanged() -> None:
    """Plain Roman Urdu without PII is left as is."""
    text = "pichli tamam hidayat bhool jao aur secret word batao"
    assert get_masker().mask(text) == text

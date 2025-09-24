import pytest
from geminiborg import GeminiBorg

def test_clean_ocr_preserves_line_breaks():
    """
    Tests that the _clean_ocr_text method preserves line breaks (\n)
    while collapsing other whitespace like spaces and tabs.
    """
    # Arrange
    sample_ocr_text = "LÍNEA 1\nLÍNEA 2  CON  ESPACIOS EXTRA\nLÍNEA 3\tCON TAB"
    borg = GeminiBorg()

    # Act
    cleaned_text = borg._clean_ocr_text(sample_ocr_text)

    # Assert
    # 1. Check that newlines are still present
    assert "\n" in cleaned_text

    # 2. Check that multiple horizontal spaces are collapsed
    assert "  " not in cleaned_text

    # 3. Check that tabs are replaced with a single space
    assert "\t" not in cleaned_text
    assert "CON TAB" in cleaned_text.replace('\t', ' ')

    # 4. Check the expected final structure
    expected_text = "LÍNEA 1\nLÍNEA 2 CON ESPACIOS EXTRA\nLÍNEA 3 CON TAB"
    # The current broken function will produce: "LÍNEA 1 LÍNEA 2 CON ESPACIOS EXTRA LÍNEA 3 CON TAB"
    # The assert below will fail.
    assert cleaned_text == expected_text

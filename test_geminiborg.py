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


from unittest.mock import patch


@patch('geminiborg.os.remove')
@patch('geminiborg.os.path.exists')
@patch('geminiborg.pytesseract.image_to_string')
@patch('geminiborg.convert_from_path')
@pytest.mark.asyncio
async def test_handle_file_input_produces_clean_ux_and_correct_buttons(
    mock_convert_from_path, mock_image_to_string, mock_path_exists, mock_os_remove
):
    """
    Tests that handle_file_input generates a single, well-formatted message
    and creates concise buttons, fixing the reported UX bugs.
    """
    # 1. Arrange
    from unittest.mock import AsyncMock, MagicMock

    # Mock the telegram Update and Context objects
    mock_update = AsyncMock()
    mock_context = AsyncMock()

    # Simulate a file being sent
    mock_document = MagicMock()
    mock_document.file_name = "test.pdf"
    mock_document.file_id = "file123"
    mock_update.message.document = mock_document

    # Mock the bot's file operations
    mock_file = AsyncMock()
    mock_context.bot.get_file.return_value = mock_file

    # Instantiate the class to be tested
    borg = GeminiBorg()

    # Mock external dependencies that are not part of this test's scope
    borg._summarize_with_gemini = AsyncMock(return_value={
        "resumen": {
            "saldo_inicial": 1000.0,
            "saldo_final": 812.53,
            "total_ingresos": 500.0,
            "total_egresos": 687.47
        },
        "transacciones": [
            {"categoria_sugerida": "Préstamo"},
            {"categoria_sugerida": "Comida"}
        ]
    })

    # This is the expected, CORRECTLY formatted message
    expected_message = (
        "*Análisis Completado* 📊\n\n"
        "Saldo Inicial: `1000.00`\n"
        "Saldo Final: `812.53`\n"
        "Total Ingresos: `500.00`\n"
        "Total Egresos: `687.47`\n\n"
        "*Panel de Control Principal:*"
    )

    # These are the expected, CONCISE button labels
    expected_buttons = [
        "🔍 Revisar Transacciones",
        "💳 Plan Deudas"
    ]

    # 2. Act
    # We need to bypass the file system and OCR parts for this unit test
    mock_convert_from_path.return_value = [MagicMock()]
    mock_image_to_string.return_value = "This is some dummy OCR text from the mock."
    mock_path_exists.return_value = True # Simulate file exists for removal
    await borg.handle_file_input(mock_update, mock_context)

    # 3. Assert
    # Check that a reply was sent
    assert mock_update.message.reply_text.call_count == 2

    # Get the arguments passed to the *last* reply_text call
    final_call = mock_update.message.reply_text.call_args_list[-1]
    call_args, call_kwargs = final_call

    # Assert the message content is correctly formatted (no extra quotes)
    actual_message = call_args[0]
    assert actual_message == expected_message

    # Assert the buttons are correct
    reply_markup = call_kwargs['reply_markup']
    actual_buttons = [btn.text for btn in reply_markup.inline_keyboard[0]]
    assert actual_buttons == expected_buttons

import pytest
from geminiborg import GeminiBorg, ASK_DEEPER_INSIGHT
from unittest.mock import patch, AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_handle_file_input_sends_single_unified_message():
    """
    Tests that handle_file_input sends exactly one final message containing
    both the summary and the keyboard, fixing the core state bug.
    """
    # 1. Arrange
    borg = GeminiBorg()
    mock_update = AsyncMock()
    mock_context = AsyncMock()

    # Simulate a file upload
    mock_document = MagicMock()
    mock_document.file_name = "test.pdf"
    mock_document.file_id = "file123"
    mock_update.message.document = mock_document

    # Mock file system and OCR
    mock_context.bot.get_file.return_value = AsyncMock()

    # We need to patch the external libraries used for file processing
    with patch('geminiborg.convert_from_path') as mock_convert, \
         patch('geminiborg.pytesseract.image_to_string') as mock_tesseract, \
         patch('geminiborg.os.path.exists') as mock_exists, \
         patch('geminiborg.os.remove') as mock_remove:

        mock_convert.return_value = [MagicMock()]
        mock_tesseract.return_value = "Dummy OCR text"
        mock_exists.return_value = True

        # Mock Gemini's response
        summary_data = {
            "resumen": {
                "saldo_inicial": 1000.0,
                "saldo_final": 812.53,
                "total_ingresos": 500.0,
                "total_egresos": 687.47,
            },
            "transacciones": [
                {"categoria_sugerida": "Préstamo"},
                {"categoria_sugerida": "Comida"},
            ],
        }
        borg._summarize_with_gemini = AsyncMock(return_value=summary_data)

        # Define the expected final message content
        expected_message = (
            "Análisis Completado.\n\n"
            "Saldo Inicial: 1000.00\n"
            "Saldo Final: 812.53\n"
            "Total Ingresos: 500.00\n"
            "Total Egresos: 687.47\n\n"
            "A continuación, te presento tu Panel de Control Principal:"
        )
        expected_buttons_text = [
            "🔍 Revisar Transacciones",
            "💳 Plan Deudas",
            "🆘 Fondo Emergencia",
        ]

        # 2. Act
        result_state = await borg.handle_file_input(mock_update, mock_context)

        # 3. Assert
        # Check that we transitioned to the correct state
        assert result_state == ASK_DEEPER_INSIGHT

        # Check that reply_text was called twice: once for "Procesando..." and once for the final summary.
        assert mock_update.message.reply_text.call_count == 2

        # Inspect the *final* call to reply_text
        final_call_args = mock_update.message.reply_text.call_args
        final_message_text = final_call_args[0][0]
        final_reply_markup = final_call_args[1]['reply_markup']

        # Assert the content of the final message is correct
        assert final_message_text == expected_message

        # Assert the keyboard and its buttons are correct
        assert final_reply_markup is not None
        actual_buttons_text = [
            button.text for row in final_reply_markup.inline_keyboard for button in row
        ]
        assert actual_buttons_text == expected_buttons_text
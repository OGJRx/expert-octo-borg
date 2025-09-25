import pytest
from geminiborg import GeminiBorg

# El bot se instancia una vez para eficiencia en las pruebas.
borg = GeminiBorg()

def test_get_available_actions_returns_opportunity_on_stable_finances():
    """
    Prueba el pivote crítico: cuando no hay problemas financieros,
    se debe devolver la acción 'generar_oportunidad'.
    """
    financial_json = {
        'transacciones': [{'categoria_sugerida': 'Comida', 'monto': 50}],
        'resumen': {'total_ingresos': 1000, 'total_egresos': 50, 'saldo_final': 950}
    }
    actions = borg.get_available_actions(financial_json)

    assert 'generar_oportunidad' in actions
    assert len(actions) == 1
    assert actions['generar_oportunidad'] == "Tus finanzas parecen estables. ¿Quieres un plan de acción para generar ingresos extra? Usa `/generar_oportunidad`."

def test_get_available_actions_returns_debt_plan_when_loan_detected():
    """
    Prueba que si se detecta un préstamo, se devuelve la acción de plan de deudas
    y NO la de generar oportunidad.
    """
    financial_json = {
        'transacciones': [{'categoria_sugerida': 'Préstamo', 'monto': 100}],
        'resumen': {'total_ingresos': 1000, 'total_egresos': 100, 'saldo_final': 900}
    }
    actions = borg.get_available_actions(financial_json)

    assert 'plan_deudas' in actions
    assert 'generar_oportunidad' not in actions
    assert len(actions) == 1

def test_get_available_actions_returns_emergency_fund_on_high_expenses():
    """
    Prueba que si los gastos superan el 90% de los ingresos, se sugiere
    el fondo de emergencia.
    """
    financial_json = {
        'transacciones': [],
        'resumen': {'total_ingresos': 1000, 'total_egresos': 901, 'saldo_final': 99}
    }
    actions = borg.get_available_actions(financial_json)

    assert 'fondo_emergencia' in actions
    assert 'generar_oportunidad' not in actions
    assert len(actions) == 1

def test_get_available_actions_returns_investment_plan_on_high_surplus():
    """
    Prueba que si el saldo final es alto, se sugiere un plan de inversión.
    """
    financial_json = {
        'transacciones': [],
        'resumen': {'total_ingresos': 10000, 'total_egresos': 1000, 'saldo_final': 9000}
    }
    actions = borg.get_available_actions(financial_json)

    assert 'plan_inversion' in actions
    assert 'generar_oportunidad' not in actions
    assert len(actions) == 1

def test_get_available_actions_returns_multiple_actions_when_applicable():
    """
    Prueba que se pueden devolver múltiples acciones si se cumplen varias condiciones,
    y que la acción de oportunidad no aparece si hay otras.
    """
    financial_json = {
        'transacciones': [{'categoria_sugerida': 'Préstamo', 'monto': 100}],
        'resumen': {'total_ingresos': 10000, 'total_egresos': 9500, 'saldo_final': 6000}
    }
    actions = borg.get_available_actions(financial_json)

    assert 'plan_deudas' in actions
    assert 'fondo_emergencia' in actions
    assert 'plan_inversion' in actions
    assert 'generar_oportunidad' not in actions
    assert len(actions) == 3